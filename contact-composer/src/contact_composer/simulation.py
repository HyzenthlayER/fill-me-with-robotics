"""M07: torque-only forward replay, separate from kinematic preview."""

import time
from dataclasses import dataclass, field

import mujoco
import numpy as np

from .controller import command
from .diagnostics import Issue
from .model import RobotModel, anchor_point
from .planning import StopSolve, check_stop
from .schedule import Schedule
from .spec import EFFECTORS
from .trajectory import validate_trajectory


@dataclass
class ReplayResult:
    project_hash: str
    time_s: np.ndarray
    q_measured: np.ndarray
    dq_measured: np.ndarray
    tau_commanded: np.ndarray
    measured_endpoint_world: np.ndarray
    actual_contact_forces_world: np.ndarray
    status: str
    checks: dict = field(default_factory=dict)
    issues: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def arrays(self):
        return {k: v for k, v in vars(self).items() if isinstance(v, np.ndarray)}

    def summary(self):
        return {
            "project_hash": self.project_hash,
            "status": self.status,
            "samples": len(self.time_s),
            "checks": self.checks,
            "issues": [i.to_dict() for i in self.issues],
            "metadata": self.metadata,
        }


def interpolate(trajectory, t, key):
    values = getattr(trajectory, key)
    flat = values.reshape(len(values), -1)
    return np.array(
        [np.interp(t, trajectory.time_s, flat[:, i]) for i in range(flat.shape[1])]
    ).reshape(values.shape[1:])


def replay(project, trajectory, progress=None, cancel=None):
    if project.digest() != trajectory.project_hash:
        raise ValueError("STALE_RESULT: trajectory belongs to another project revision")
    if trajectory.check_status != "passed" or trajectory.solve_status != "success":
        raise ValueError(
            "Replay requires a complete candidate with passed planning checks"
        )
    if validate_trajectory(project, trajectory):
        raise ValueError("Replay requires independently validated trajectory arrays")
    started = time.monotonic()
    robot = RobotModel(project)
    schedule = Schedule(project)
    config = project.settings.replay
    data = mujoco.MjData(robot.mj)
    # The only writes of generalized position/velocity to the simulator are initialization.
    data.qpos[:] = project.initial_state.q
    data.qvel[:] = project.initial_state.dq
    mujoco.mj_forward(robot.mj, data)
    dt = config.physics_dt
    stride = round(config.control_dt / dt)
    duration = project.timeline.duration_ticks * 0.05
    steps = round(duration / dt)
    logs = {k: [] for k in ("time", "q", "dq", "tau", "endpoint", "force")}
    loss = np.zeros(4)
    max_loss = 0.0
    max_drift = 0.0
    max_penetration = 0.0
    unexpected_duration = 0.0
    max_unexpected = 0.0
    issues = []
    pair_records = []
    saturated = 0
    controls = 0
    status = "completed"
    raw = np.zeros(8)

    def record():
        nonlocal \
            max_loss, \
            max_drift, \
            max_penetration, \
            unexpected_duration, \
            max_unexpected
        t = float(data.time)
        tick = min(t / 0.05, schedule.duration)
        measured = np.zeros((4, 2))
        active = {c.effector_id: c for c in schedule.active(tick)}
        unexpected = False
        pairs = []
        for contact_index, c in enumerate(data.contact[: data.ncon]):
            force_local = np.zeros(6)
            mujoco.mj_contactForce(robot.mj, data, contact_index, force_local)
            g1, g2 = int(c.geom1), int(c.geom2)
            force = c.frame.reshape(3, 3).T @ force_local[:3]
            if robot.mj.geom_bodyid[g1] != 0:
                robot_geom, other, force = g1, g2, -force
            else:
                robot_geom, other = g2, g1
            name = robot.mj.geom(robot_geom).name
            other_name = robot.mj.geom(other).name
            normal_load = float(abs(force_local[0]))
            pairs.append(
                {
                    "robot_geom": name,
                    "other_geom": other_name,
                    "force_world": force[[0, 2]].tolist(),
                    "distance": float(c.dist),
                }
            )
            effector = next((e for e in EFFECTORS if name == e + "_geom"), None)
            intended = (
                effector in active
                and other_name == f"surface_{active[effector].surface_id}"
            )
            if intended:
                measured[EFFECTORS.index(effector)] += force[[0, 2]]
            elif normal_load > 0.01 * robot.weight:
                unexpected = True
            max_penetration = max(max_penetration, -float(c.dist))
        point = data.site_xpos[robot.sites][:, [0, 2]].copy()
        planned = interpolate(trajectory, t, "contact_force_world")
        for e, name in enumerate(EFFECTORS):
            contact = active.get(name)
            if contact is not None:
                normal = np.asarray(schedule.surfaces[contact.surface_id].normal)
                loaded = float(planned[e] @ normal) > 0.02 * robot.weight
                if loaded:
                    max_drift = max(
                        max_drift,
                        float(
                            np.linalg.norm(point[e] - anchor_point(project, contact))
                        ),
                    )
                    loss[e] = (
                        loss[e] + config.control_dt
                        if measured[e] @ normal < 0.01 * robot.weight
                        else 0
                    )
                else:
                    loss[e] = 0
            else:
                loss[e] = 0
        max_loss = max(max_loss, float(loss.max()))
        unexpected_duration = (
            unexpected_duration + config.control_dt if unexpected else 0
        )
        max_unexpected = max(max_unexpected, unexpected_duration)
        for key, value in (
            ("time", t),
            ("q", data.qpos.copy()),
            ("dq", data.qvel.copy()),
            ("tau", data.ctrl.copy()),
            ("endpoint", point),
            ("force", measured),
        ):
            logs[key].append(value)
        pair_records.append(pairs)

    record()
    try:
        for step in range(steps):
            if step % stride == 0:
                check_stop(None, cancel)
                t = float(data.time)
                qref = interpolate(trajectory, t, "q")
                dqref = interpolate(trajectory, t, "dq")
                if config.controller == "whole_body":
                    raw = command(
                        robot,
                        schedule,
                        data.qpos.copy(),
                        data.qvel.copy(),
                        qref,
                        dqref,
                        interpolate(trajectory, t, "ddq"),
                        interpolate(trajectory, t, "contact_force_world"),
                        t / 0.05,
                    )
                else:
                    raw = (
                        interpolate(trajectory, t, "tau_reference")
                        + config.kp * (qref[3:] - data.qpos[3:])
                        + config.kd * (dqref[3:] - data.qvel[3:])
                    )
                saturated += int(np.any(np.abs(raw) > robot.torque_limits))
                controls += 1
                data.ctrl[:] = np.clip(raw, -robot.torque_limits, robot.torque_limits)
            mujoco.mj_step(robot.mj, data)
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                status = "nonfinite"
                break
            if (step + 1) % stride == 0 or step + 1 == steps:
                mujoco.mj_forward(robot.mj, data)
                record()
                if progress and (step + 1) % (stride * 20) == 0:
                    progress(
                        (step + 1) / steps,
                        f"Simulating {data.time:.2f} / {duration:.2f} s",
                    )
                if data.qpos[1] < 0.15 or abs(data.qpos[2]) > 1.3:
                    status = "fell"
                    break
    except StopSolve:
        status = "cancelled"
    except RuntimeError as error:
        status = "controller_failed"
        issues.append(
            Issue(
                "CONTROLLER_FAILED",
                str(error),
                (float(data.time), float(data.time)),
                source="simulation",
            )
        )
    times = np.asarray(logs["time"])
    qs = np.asarray(logs["q"])
    reference = np.asarray([interpolate(trajectory, t, "q") for t in times])
    errors = qs - reference
    checks = {
        "joint_rms_rad": float(np.sqrt(np.mean(errors[:, 3:] ** 2))),
        "base_error_m": float(np.linalg.norm(errors[:, :2], axis=1).max()),
        "pitch_error_rad": float(np.abs(errors[:, 2]).max()),
        "drift_m": max_drift,
        "support_loss_s": max_loss,
        "penetration_m": max_penetration,
        "unexpected_contact_s": max_unexpected,
        "saturation_fraction": saturated / max(controls, 1),
        "joint_limit_excess_rad": float(max(np.max(np.abs(qs[:, 3:]) - 2.6), 0)),
    }
    limits = {
        "joint_rms_rad": config.joint_rms_rad,
        "base_error_m": config.base_error_m,
        "pitch_error_rad": config.pitch_error_rad,
        "drift_m": config.drift_m,
        "support_loss_s": config.support_loss_s,
        "penetration_m": config.penetration_m,
        "unexpected_contact_s": 0.1,
        "saturation_fraction": config.saturation_fraction,
        "joint_limit_excess_rad": 0.01,
    }
    codes = {
        "drift_m": "CONTACT_DRIFT",
        "support_loss_s": "CONTACT_LOSS",
        "penetration_m": "COLLISION",
        "unexpected_contact_s": "UNEXPECTED_CONTACT",
        "saturation_fraction": "TORQUE_SATURATION",
        "joint_limit_excess_rad": "JOINT_LIMIT",
    }
    for key, value in checks.items():
        if value > limits[key]:
            issues.append(
                Issue(
                    codes.get(key, "TRACKING_ERROR"),
                    key,
                    (0, float(times[-1])),
                    measured=value,
                    limit=limits[key],
                    source="simulation",
                    scope="this replay",
                )
            )
    if status != "completed":
        issues.append(
            Issue(
                "REPLAY_STOPPED",
                status,
                (float(times[-1]), float(times[-1])),
                source="simulation",
                scope="this replay",
            )
        )
    final_status = (
        "passed"
        if status == "completed" and not issues
        else ("cancelled" if status == "cancelled" else "failed")
    )
    return ReplayResult(
        project.digest(),
        times,
        qs,
        np.asarray(logs["dq"]),
        np.asarray(logs["tau"]),
        np.asarray(logs["endpoint"]),
        np.asarray(logs["force"]),
        final_status,
        checks,
        issues,
        {
            "elapsed_s": time.monotonic() - started,
            "engine": "mujoco",
            "engine_version": mujoco.__version__,
            "controller": config.controller,
            "settings": config.model_dump(),
            "stop_reason": status,
            "planar_base": True,
            "hidden_support_forces": False,
            "settling_s": 0.0,
            "contact_pairs": pair_records,
            "limits": limits,
        },
    )

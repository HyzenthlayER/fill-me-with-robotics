"""M02: one original MJCF model for planning, geometry, and dynamics."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET

import mujoco
import numpy as np

from .project import Project, Surface
from .spec import EFFECTORS, MODEL_HASH, SPEC


def vector(values):
    return " ".join(str(float(v)) for v in values)


def surface_frame(surface: Surface):
    a, b = np.asarray(surface.segment_start), np.asarray(surface.segment_end)
    return (b - a) / np.linalg.norm(b - a), np.asarray(surface.normal)


def anchor_point(project: Project, contact, center=True):
    surface = next(s for s in project.surfaces if s.id == contact.surface_id)
    point = (
        np.asarray(surface.segment_start) * (1 - contact.anchor_u)
        + np.asarray(surface.segment_end) * contact.anchor_u
    )
    return point + SPEC["radius"] * np.asarray(surface.normal) if center else point


def build_xml(project: Project) -> str:
    root = ET.Element("mujoco", model="contact-composer-planar")
    ET.SubElement(root, "compiler", angle="radian", autolimits="true")
    ET.SubElement(
        root,
        "option",
        timestep=str(project.settings.replay.physics_dt),
        gravity="0 0 -9.81",
        integrator="implicitfast",
        solver="Newton",
        iterations="100",
        tolerance="1e-10",
    )
    default = ET.SubElement(root, "default")
    ET.SubElement(
        default,
        "geom",
        contype="1",
        conaffinity="2",
        condim="3",
        friction="0.8 0 0",
        solref="0.005 1",
        solimp="0.95 0.99 0.001",
        margin="0",
    )
    ET.SubElement(default, "joint", damping="0", armature="0.005")
    world = ET.SubElement(root, "worldbody")
    for surface in project.surfaces:
        a, b = np.asarray(surface.segment_start), np.asarray(surface.segment_end)
        tangent, normal = surface_frame(surface)
        center = (a + b) / 2 - normal * 0.025
        angle = -math.atan2(tangent[1], tangent[0])
        ET.SubElement(
            world,
            "geom",
            name=f"surface_{surface.id}",
            type="box",
            pos=vector([center[0], 0, center[1]]),
            size=vector([np.linalg.norm(b - a) / 2, 0.15, 0.025]),
            quat=vector([math.cos(angle / 2), 0, math.sin(angle / 2), 0]),
            contype="2",
            conaffinity="1",
            priority="1",
            friction=f"{surface.mu} 0 0",
        )
    for obstacle in project.obstacles:
        ET.SubElement(
            world,
            "geom",
            name=f"obstacle_{obstacle.id}",
            type="box",
            pos=vector([obstacle.position[0], 0, obstacle.position[1]]),
            size=vector([obstacle.dimensions[0] / 2, 0.15, obstacle.dimensions[1] / 2]),
            contype="2",
            conaffinity="1",
        )
    base = ET.SubElement(world, "body", name="torso")
    ET.SubElement(
        base, "joint", name="base_x", type="slide", axis="1 0 0", armature="0"
    )
    ET.SubElement(
        base, "joint", name="base_z", type="slide", axis="0 0 1", armature="0"
    )
    ET.SubElement(
        base, "joint", name="base_pitch", type="hinge", axis="0 1 0", armature="0"
    )
    ET.SubElement(
        base,
        "geom",
        name="torso_geom",
        type="box",
        pos="0 0 0.15",
        size="0.085 0.065 0.15",
        mass=str(SPEC["torso_mass"]),
    )
    for i, effector in enumerate(EFFECTORS):
        leg = i < 2
        side = i % 2
        lengths = SPEC["leg_lengths"] if leg else SPEC["arm_lengths"]
        masses = SPEC["leg_masses"] if leg else SPEC["arm_masses"]
        offset = (SPEC["hip_offsets"] if leg else SPEC["shoulder_offsets"])[side]
        height = 0.0 if leg else SPEC["shoulder_height"]
        prefix = "left" if side == 0 else "right"
        joint_names = (
            [f"{prefix}_hip", f"{prefix}_knee"]
            if leg
            else [f"{prefix}_shoulder", f"{prefix}_elbow"]
        )
        parent = base
        for j, (length, mass, joint_name) in enumerate(
            zip(lengths, masses, joint_names)
        ):
            body = ET.SubElement(
                parent,
                "body",
                name=joint_name + "_link",
                pos=vector([offset, 0, height])
                if j == 0
                else vector([0, 0, -lengths[0]]),
            )
            ET.SubElement(
                body,
                "joint",
                name=joint_name,
                type="hinge",
                axis="0 1 0",
                range="-2.6 2.6",
            )
            ET.SubElement(
                body,
                "geom",
                name=joint_name + "_geom",
                type="capsule",
                fromto=vector([0, 0, -0.035, 0, 0, -length + 0.035]),
                size="0.014",
                mass=str(mass),
            )
            parent = body
        ET.SubElement(
            parent,
            "geom",
            name=effector + "_geom",
            type="sphere",
            pos=vector([0, 0, -lengths[1]]),
            size=str(SPEC["radius"]),
            mass=str(SPEC["endpoint_mass"]),
        )
        ET.SubElement(
            parent, "site", name=effector, pos=vector([0, 0, -lengths[1]]), size="0.004"
        )
    contacts = ET.SubElement(root, "contact")
    # Deliberate planar model: overlapping left/right limb pairs are excluded.
    # Endpoints against torso are the explicit nonadjacent self-collision pairs.
    for effector in EFFECTORS:
        ET.SubElement(
            contacts, "pair", geom1="torso_geom", geom2=effector + "_geom", condim="3"
        )
    actuators = ET.SubElement(root, "actuator")
    for name, limit in zip(SPEC["joint_names"], SPEC["torque_limits"]):
        ET.SubElement(
            actuators,
            "motor",
            name=name + "_motor",
            joint=name,
            gear="1",
            ctrllimited="true",
            ctrlrange=f"{-limit} {limit}",
        )
    return ET.tostring(root, encoding="unicode")


class RobotModel:
    def __init__(self, project: Project):
        self.project = project
        self.xml = build_xml(project)
        self.mj = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(self.mj)
        self.mass = float(self.mj.body_mass.sum())
        self.weight = self.mass * 9.81
        self.torque_limits = np.asarray(SPEC["torque_limits"])
        self.sites = [self.mj.site(name).id for name in EFFECTORS]
        self.environment_geoms = [
            i for i in range(self.mj.ngeom) if self.mj.geom_bodyid[i] == 0
        ]
        self.robot_geoms = [
            i for i in range(self.mj.ngeom) if self.mj.geom_bodyid[i] != 0
        ]
        self.collision_pairs = [
            (a, b) for a in self.robot_geoms for b in self.environment_geoms
        ]
        self.collision_pairs += [
            (self.mj.geom("torso_geom").id, self.mj.geom(e + "_geom").id)
            for e in EFFECTORS
        ]
        self.force_scale = np.full(11, self.weight)
        self.force_scale[2:] *= SPEC["characteristic_length"]

    def forward(self, q, dq=None):
        self.data.qpos[:] = q
        self.data.qvel[:] = 0 if dq is None else dq
        self.data.ctrl[:] = 0
        mujoco.mj_forward(self.mj, self.data)
        return self.data

    def endpoints(self, q):
        self.forward(q)
        return self.data.site_xpos[self.sites][:, [0, 2]].copy()

    def jacobian(self, effector, normal=None):
        index = EFFECTORS.index(effector)
        site = self.sites[index]
        jac = np.zeros((3, self.mj.nv))
        if normal is None:
            mujoco.mj_jacSite(self.mj, self.data, jac, None, site)
        else:
            point = self.data.site_xpos[site].copy()
            point[[0, 2]] -= SPEC["radius"] * np.asarray(normal)
            mujoco.mj_jac(
                self.mj, self.data, jac, None, point, int(self.mj.site_bodyid[site])
            )
        return jac[[0, 2]]

    def gravity(self, q):
        self.forward(q)
        return self.data.qfrc_bias.copy()

    def center_of_mass(self, q):
        self.forward(q)
        return (self.mj.body_mass[:, None] * self.data.xipos).sum(axis=0)[
            [0, 2]
        ] / self.mass

    def distances(self, q):
        self.forward(q)
        # Some convex pairs return zero distance while already intersecting.
        # Collision-generated signed distances supply the penetration depth.
        penetrations = {}
        for contact in self.data.contact[: self.data.ncon]:
            key = tuple(sorted((int(contact.geom1), int(contact.geom2))))
            penetrations[key] = min(penetrations.get(key, 0.0), float(contact.dist))
        return np.asarray(
            [
                min(
                    mujoco.mj_geomDistance(self.mj, self.data, a, b, 10.0, None),
                    penetrations.get(tuple(sorted((a, b))), float("inf")),
                )
                for a, b in self.collision_pairs
            ]
        )

    def segments(self, q):
        self.forward(q)
        lines = []
        for effector in EFFECTORS:
            site = self.mj.site(effector).id
            distal = int(self.mj.site_bodyid[site])
            proximal = int(self.mj.body_parentid[distal])
            points = np.array(
                [
                    self.data.xpos[proximal],
                    self.data.xpos[distal],
                    self.data.site_xpos[site],
                ]
            )[:, [0, 2]]
            lines.append({"effector": effector, "points": points.tolist()})
        return {
            "limbs": lines,
            "base": np.asarray(q[:3]).tolist(),
            "com": self.center_of_mass(q).tolist(),
            "endpoints": self.endpoints(q).tolist(),
        }

    def inverse_endpoints(self, base_q, targets, reference):
        """Exact two-link IK with the nearest joint-limit-valid elbow branch."""
        q = np.asarray(reference, dtype=float).copy()
        q[:3] = base_q
        angle = q[2]
        rotation = np.array(
            [[math.cos(angle), math.sin(angle)], [-math.sin(angle), math.cos(angle)]]
        )
        for i, target in enumerate(targets):
            leg = i < 2
            side = i % 2
            offset = (SPEC["hip_offsets"] if leg else SPEC["shoulder_offsets"])[side]
            origin = np.array([offset, 0 if leg else SPEC["shoulder_height"]])
            local = rotation.T @ (target - q[:2]) - origin
            l1, l2 = SPEC["leg_lengths"] if leg else SPEC["arm_lengths"]
            cosine = (local @ local - l1 * l1 - l2 * l2) / (2 * l1 * l2)
            if abs(cosine) > 1 + 1e-9:
                return None
            candidates = []
            for second in (
                math.acos(np.clip(cosine, -1, 1)),
                -math.acos(np.clip(cosine, -1, 1)),
            ):
                first = math.atan2(-local[0], -local[1]) - math.atan2(
                    l2 * math.sin(second), l1 + l2 * math.cos(second)
                )
                first = (first + math.pi) % (2 * math.pi) - math.pi
                pair = np.array([first, second])
                if np.max(np.abs(pair)) <= 2.6:
                    candidates.append(pair)
            if not candidates:
                return None
            index = 3 + 2 * i
            q[index : index + 2] = min(
                candidates,
                key=lambda pair: np.linalg.norm(pair - reference[index : index + 2]),
            )
        return q

    def manifest(self):
        torso = self.mj.geom("torso_geom").id
        return {
            **SPEC,
            "model_hash": MODEL_HASH,
            "total_mass": self.mass,
            "torso_center": self.mj.geom_pos[torso][[0, 2]].tolist(),
            "torso_half_size": self.mj.geom_size[torso][[0, 2]].tolist(),
            "collision_pairs": [
                [self.mj.geom(a).name, self.mj.geom(b).name]
                for a, b in self.collision_pairs
            ],
            "q_order": [self.mj.joint(i).name for i in range(self.mj.njnt)],
        }

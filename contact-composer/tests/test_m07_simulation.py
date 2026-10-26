import numpy as np
import pytest

from contact_composer.model import RobotModel
from contact_composer.project import standing_project
from contact_composer.simulation import replay
from contact_composer.trajectory import generate


def test_torque_driven_standing_replay_and_force_sign():
    p = standing_project(40)
    trajectory = generate(p)
    result = replay(p, trajectory)
    assert result.status == "passed", result.summary()
    np.testing.assert_allclose(result.q_measured[0], p.initial_state.q)
    assert (
        np.max(np.abs(result.q_measured - trajectory.q[: len(result.q_measured)]))
        > 1e-6
    )
    weight = RobotModel(p).weight
    assert (
        abs(result.actual_contact_forces_world[-20:, :, 1].sum(axis=1).mean() - weight)
        < 0.03 * weight
    )
    assert result.metadata["hidden_support_forces"] is False


def test_stale_and_unvalidated_candidates_are_rejected():
    p = standing_project(40)
    trajectory = generate(p)
    changed = p.model_copy(deep=True)
    changed.revision += 1
    with pytest.raises(ValueError, match="STALE_RESULT"):
        replay(changed, trajectory)
    trajectory.check_status = "failed"
    with pytest.raises(ValueError, match="passed planning checks"):
        replay(p, trajectory)


def test_cancel_replay_retains_partial_evidence():
    p = standing_project(40)
    trajectory = generate(p)
    result = replay(p, trajectory, cancel=lambda: True)
    assert result.status == "cancelled"
    assert len(result.time_s) == 1


def test_unstable_gains_are_reported_as_failure():
    p = standing_project(40)
    p.settings.replay.kp = 180
    p.settings.replay.kd = 12
    p.settings.replay.controller = "joint_pd"
    result = replay(p, generate(p))
    assert result.status == "failed"
    assert any(i.code == "TORQUE_SATURATION" for i in result.issues)


def test_complete_wall_assisted_demo():
    from contact_composer.examples import wall_assisted

    p = wall_assisted()
    trajectory = generate(p)
    assert trajectory.check_status == "passed", trajectory.summary()
    result = replay(p, trajectory)
    assert result.status == "passed", result.summary()
    middle = (result.time_s > 5) & (result.time_s < 7)
    assert (
        np.mean(result.actual_contact_forces_world[middle, 3, 0])
        < -0.01 * RobotModel(p).weight
    )
    assert result.checks["base_error_m"] < 0.03

import time

import numpy as np
import pytest

from contact_composer.model import RobotModel
from contact_composer.planning import StopSolve, allocate_forces, solve_pose
from contact_composer.project import standing_project
from contact_composer.schedule import Schedule


def test_static_force_balance_and_inactive_forces():
    p = standing_project()
    r = RobotModel(p)
    s = Schedule(p)
    result = allocate_forces(r, s, p.initial_state.q, 0)
    assert result.success, result.message
    assert result.residual < 1e-7
    np.testing.assert_allclose(result.forces.sum(axis=0), [0, r.weight], atol=1e-5)
    np.testing.assert_array_equal(result.forces[2:], 0)
    assert np.all(np.abs(result.tau) < r.torque_limits)


def test_fixed_pose_single_point_support_cannot_balance_offset_com():
    p = standing_project()
    p.contacts = p.contacts[:1]
    r = RobotModel(p)
    s = Schedule(p)
    result = allocate_forces(r, s, p.initial_state.q, 0)
    assert result.status == "fixed_pose_infeasible"
    assert result.forces is None


def test_force_cap_insufficient_and_zero_contact():
    p = standing_project()
    p.surfaces[0].force_cap_n = 1
    r = RobotModel(p)
    assert not allocate_forces(r, Schedule(p), p.initial_state.q, 0).success
    p.contacts = []
    assert not allocate_forces(r, Schedule(p), p.initial_state.q, 0).success


def test_pose_solver_preserves_standing_and_respects_deadline():
    p = standing_project()
    r = RobotModel(p)
    s = Schedule(p)
    q = np.asarray(p.initial_state.q)
    endpoints = r.endpoints(q)
    result = solve_pose(r, s, 0, q, endpoints)
    assert result.status == "success", result
    assert result.residuals["contact"] < 1e-6
    with pytest.raises(StopSolve, match="timeout"):
        solve_pose(r, s, 0, q, endpoints, deadline=time.monotonic() - 1)
    with pytest.raises(StopSolve, match="cancelled"):
        solve_pose(r, s, 0, q, endpoints, cancel=lambda: True)


def test_unreachable_anchor_is_not_success():
    p = standing_project()
    p.contacts[0].anchor_u = 0.01
    p.contacts[1].anchor_u = 0.99
    p.settings.planning.max_iterations = 12
    r = RobotModel(p)
    q = np.asarray(p.initial_state.q)
    result = solve_pose(r, Schedule(p), 0, q, r.endpoints(q))
    assert result.status == "no_solution_found"


def test_wall_support_is_necessary_at_the_demo_peak_pose():
    from contact_composer.examples import wall_assisted

    p = wall_assisted()
    robot = RobotModel(p)
    q = np.array(p.initial_state.q)
    pose = solve_pose(robot, Schedule(p), 120, q, robot.endpoints(q))
    assert pose.status == "success"
    without_hand = p.model_copy(deep=True)
    without_hand.contacts = [c for c in p.contacts if c.effector_id != "right_hand"]
    result = allocate_forces(robot, Schedule(without_hand), pose.q, 120)
    assert result.status == "fixed_pose_infeasible"
    frictionless = p.model_copy(deep=True)
    frictionless.surfaces[0].mu = 0
    result = allocate_forces(robot, Schedule(frictionless), pose.q, 120)
    assert result.status == "fixed_pose_infeasible"

import numpy as np

from contact_composer.model import RobotModel, anchor_point
from contact_composer.project import Obstacle, standing_project
from contact_composer.spec import EFFECTORS, Q0


def test_dimensions_mapping_and_standing_anchors():
    project = standing_project()
    robot = RobotModel(project)
    assert (robot.mj.nq, robot.mj.nv, robot.mj.nu) == (11, 11, 8)
    np.testing.assert_array_equal(robot.mj.actuator_trnid[:, 0], np.arange(3, 11))
    points = robot.endpoints(Q0)
    for i, contact in enumerate(project.contacts):
        np.testing.assert_allclose(
            points[i], anchor_point(project, contact), atol=1e-12
        )
    assert robot.distances(Q0).min() >= -1e-10


def test_jacobians_against_finite_difference():
    robot = RobotModel(standing_project())
    q = np.asarray(Q0)
    robot.forward(q)
    analytic = np.asarray([robot.jacobian(e) for e in EFFECTORS])
    numeric = np.zeros((4, 2, 11))
    for j in range(11):
        step = np.eye(11)[j] * 1e-6
        numeric[:, :, j] = (robot.endpoints(q + step) - robot.endpoints(q - step)) / (
            2e-6
        )
    np.testing.assert_allclose(analytic, numeric, atol=1e-8)


def test_gravity_matches_potential_energy_gradient():
    robot = RobotModel(standing_project())
    q = np.asarray(Q0)
    gravity = robot.gravity(q)

    def potential(q):
        robot.forward(q)
        return 9.81 * np.dot(robot.mj.body_mass, robot.data.xipos[:, 2])

    numeric = []
    for j in range(11):
        step = np.eye(11)[j] * 1e-6
        numeric.append((potential(q + step) - potential(q - step)) / (2e-6))
    np.testing.assert_allclose(gravity, numeric, atol=1e-6)
    assert abs(gravity[1] - robot.weight) < 1e-9


def test_collision_detects_obstacle():
    project = standing_project()
    project.obstacles = [
        Obstacle(id="blocked", position=(0, Q0[1] + 0.15), dimensions=(0.1, 0.1))
    ]
    robot = RobotModel(project)
    assert robot.distances(Q0).min() < -0.01

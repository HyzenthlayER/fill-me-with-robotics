import numpy as np

from contact_composer.model import RobotModel
from contact_composer.project import Contact, Project, standing_project
from contact_composer.schedule import Schedule


def test_initial_final_support_and_half_open_events():
    p = standing_project()
    p.contacts.append(
        Contact(
            id="hand",
            effector_id="right_hand",
            surface_id="wall",
            anchor_u=0.5,
            start_tick=20,
            end_tick=80,
        )
    )
    schedule = Schedule(p)
    assert len(schedule.active(20)) == 3
    assert len(schedule.active(80)) == 2
    assert len(schedule.active(120)) == 2
    assert schedule.capacity(p.contacts[0], 0) == 400
    assert schedule.capacity(p.contacts[0], 120) == 400
    assert schedule.capacity(p.contacts[2], 20) == 0
    assert schedule.capacity(p.contacts[2], 22) == 400
    assert schedule.capacity(p.contacts[2], 80) == 0
    assert [(s.start_tick, s.end_tick) for s in schedule.phases] == [
        (0, 20),
        (20, 80),
        (80, 120),
    ]


def test_approach_and_release_are_continuous_with_zero_velocity():
    p = standing_project()
    p.contacts.append(
        Contact(
            id="hand",
            effector_id="right_hand",
            surface_id="wall",
            anchor_u=0.5,
            start_tick=20,
            end_tick=80,
        )
    )
    initial = RobotModel(p).endpoints(p.initial_state.q)
    schedule = Schedule(p)
    for event in [20, 80]:
        a = schedule.tasks(event - 0.0001, initial)[3]
        b = schedule.tasks(event + 0.0001, initial)[3]
        assert np.linalg.norm(a - b) < 1e-8
        assert np.linalg.norm((b - a) / 0.0002) < 1e-5


def test_identical_adjacent_blocks_keep_support():
    data = standing_project().model_dump()
    data["contacts"][0]["end_tick"] = 60
    data["contacts"].append(
        {**data["contacts"][0], "id": "left_again", "start_tick": 60, "end_tick": 120}
    )
    schedule = Schedule(Project.model_validate(data))
    assert schedule.capacity(schedule.by_effector["left_foot"][0], 60) == 400
    assert schedule.capacity(schedule.by_effector["left_foot"][1], 60) == 400


def test_foot_swing_has_clearance_and_fixed_stance():
    data = standing_project().model_dump()
    data["contacts"][1]["end_tick"] = 30
    data["contacts"].append(
        {**data["contacts"][1], "id": "right_return", "start_tick": 90, "end_tick": 120}
    )
    p = Project.model_validate(data)
    initial = RobotModel(p).endpoints(p.initial_state.q)
    target = Schedule(p).tasks(60, initial)
    assert target[1, 1] > initial[1, 1] + 0.05
    np.testing.assert_allclose(target[0], initial[0])

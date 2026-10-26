"""Original, reproducible compositions; no third-party robot assets."""

from .project import Contact, standing_project


def wall_assisted():
    project = standing_project(240)
    project.id = "wall-assisted"
    project.name = "Wall-assisted foot lift"
    project.contacts[1].end_tick = 80
    project.contacts.append(
        Contact(
            id="right_foot_return",
            effector_id="right_foot",
            surface_id="floor",
            anchor_u=0.545,
            start_tick=160,
            end_tick=240,
        )
    )
    project.contacts.append(
        Contact(
            id="right_hand_wall",
            effector_id="right_hand",
            surface_id="wall",
            anchor_u=0.5,
            start_tick=40,
            end_tick=200,
        )
    )
    return project


def example(name):
    if name == "standing":
        return standing_project(120)
    if name == "wall-assisted":
        return wall_assisted()
    if name == "low-friction":
        project = wall_assisted()
        project.id = name
        project.name = "Insufficient wall friction"
        project.surfaces[1].mu = 0
        project.surfaces[0].mu = 0.01
        return project
    raise KeyError(name)


NAMES = ("standing", "wall-assisted", "low-friction")

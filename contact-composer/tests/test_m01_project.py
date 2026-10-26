import copy

import pytest
from pydantic import ValidationError

from contact_composer.project import (
    History,
    Project,
    parse_project,
    save_project,
    standing_project,
)


def test_round_trip_and_atomic_save(tmp_path):
    project = standing_project()
    path = tmp_path / "project.json"
    save_project(project, path)
    loaded = parse_project(path.read_text())
    assert loaded.digest() == project.digest()
    assert not list(tmp_path.glob("*.tmp"))


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version="9.0"),
        lambda d: d["initial_state"]["q"].__setitem__(0, float("nan")),
        lambda d: d["contacts"][0].update(anchor_u=1.1),
        lambda d: d["contacts"][0].update(start_tick=2.5),
        lambda d: d["contacts"][0].update(surface_id="missing"),
        lambda d: d["contacts"][0].update(mode="slide"),
        lambda d: d["surfaces"][0].update(normal=[1, 1]),
        lambda d: d.update(command="run arbitrary code"),
        lambda d: d["robot"].update(model_hash="different"),
    ],
)
def test_invalid_inputs(mutation):
    data = standing_project().model_dump()
    mutation(data)
    with pytest.raises(ValidationError):
        Project.model_validate(data)


def test_overlap_and_jump_rejected():
    data = standing_project().model_dump()
    block = copy.deepcopy(data["contacts"][0])
    block.update(id="other", start_tick=50)
    data["contacts"].append(block)
    with pytest.raises(ValidationError, match="CONTACT_CONFLICT"):
        Project.model_validate(data)
    data["contacts"][0]["end_tick"] = 50
    block["anchor_u"] = 0.6
    with pytest.raises(ValidationError, match="release interval"):
        Project.model_validate(data)


def test_history_transaction_and_monotonic_revision():
    history = History(standing_project())
    original = history.current.name
    for i in range(55):
        data = history.current.model_dump()
        data["name"] = f"Edit {i}"
        history.replace(data)
    for _ in range(55):
        history.undo()
    assert history.current.name == original
    assert history.current.revision == 110
    history.redo()
    before = history.current.digest()
    with pytest.raises(ValidationError):
        history.replace({"surfaces": []})
    assert history.current.digest() == before


def test_input_size_bound():
    with pytest.raises(ValueError, match="1 MB"):
        parse_project(" " * 1_000_001)

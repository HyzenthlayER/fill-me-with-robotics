import numpy as np
import pytest

from contact_composer.cli import main
from contact_composer.export import load_trajectory, write_bundle
from contact_composer.project import standing_project
from contact_composer.trajectory import generate


def test_bundle_roundtrip_and_tamper_detection(tmp_path):
    project = standing_project(40)
    trajectory = generate(project)
    path = tmp_path / "plan"
    write_bundle(project, trajectory, path)
    loaded, result = load_trajectory(path)
    assert loaded.digest() == project.digest()
    np.testing.assert_array_equal(result.q, trajectory.q)
    with pytest.raises(FileExistsError):
        write_bundle(project, trajectory, path)
    (path / "summary.json").write_text("{}")
    with pytest.raises(ValueError, match="Checksum mismatch"):
        load_trajectory(path)


def test_cli_example_validate_solve_and_invalid_input(tmp_path, capsys):
    path = tmp_path / "project.json"
    assert main(["example", "standing", "--output", str(path)]) == 0
    assert main(["validate", str(path)]) == 0
    assert main(["solve", str(path), "--output", str(tmp_path / "plan")]) == 0
    assert main(["example", "standing", "--output", str(path)]) == 1
    path.write_text('{"schema_version":"99"}')
    assert main(["validate", str(path)]) == 1

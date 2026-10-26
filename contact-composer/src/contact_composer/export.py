"""M10: explicit, immutable result bundles with checksums and numerical arrays."""

import hashlib
import json
import platform
import shutil
import tempfile
from importlib.metadata import version
from pathlib import Path

import numpy as np

from . import __version__
from .diagnostics import Issue
from .model import RobotModel, build_xml
from .project import parse_project
from .trajectory import Trajectory, validate_trajectory


def checksum(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_bundle(project, result, destination):
    destination = Path(destination)
    if destination.exists():
        raise FileExistsError(f"Result destination already exists: {destination}")
    if result.project_hash != project.digest():
        raise ValueError("STALE_RESULT")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".bundle-", dir=destination.parent))
    try:
        (temporary / "project.json").write_text(
            project.model_dump_json(indent=2), encoding="utf-8"
        )
        (temporary / "summary.json").write_text(
            json.dumps(result.summary(), indent=2, allow_nan=False), encoding="utf-8"
        )
        np.savez_compressed(temporary / "arrays.npz", **result.arrays())
        (temporary / "model.xml").write_text(build_xml(project), encoding="utf-8")
        kind = "trajectory" if isinstance(result, Trajectory) else "replay"
        manifest = {
            "format_version": "1.0",
            "kind": kind,
            "project_hash": project.digest(),
            "model": RobotModel(project).manifest(),
            "software": {
                "contact_composer": __version__,
                "python": platform.python_version(),
                **{
                    name: version(name) for name in ("numpy", "scipy", "mujoco", "osqp")
                },
            },
            "units": "SI",
            "force_convention": "World x,z force exerted by environment on robot",
            "array_shapes": {
                key: list(value.shape) for key, value in result.arrays().items()
            },
            "checksums": {
                name: checksum(temporary / name)
                for name in ("project.json", "summary.json", "arrays.npz", "model.xml")
            },
        }
        (temporary / "manifest.json").write_text(
            json.dumps(manifest, indent=2), encoding="utf-8"
        )
        temporary.rename(destination)
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
    return destination


def load_trajectory(path, project=None):
    path = Path(path)
    manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format_version") != "1.0" or manifest.get("kind") != "trajectory":
        raise ValueError("Unsupported bundle")
    for name in ("project.json", "summary.json", "arrays.npz", "model.xml"):
        if checksum(path / name) != manifest["checksums"].get(name):
            raise ValueError(f"Checksum mismatch: {name}")
    saved = parse_project((path / "project.json").read_text(encoding="utf-8"))
    project = project or saved
    if (
        project.digest() != saved.digest()
        or manifest["project_hash"] != project.digest()
    ):
        raise ValueError("STALE_RESULT")
    summary = json.loads((path / "summary.json").read_text(encoding="utf-8"))
    with np.load(path / "arrays.npz", allow_pickle=False) as data:
        arrays = {key: data[key] for key in data.files}
    trajectory = Trajectory(
        project_hash=project.digest(),
        **arrays,
        solve_status=summary["solve_status"],
        check_status=summary["check_status"],
        metadata=summary["metadata"],
        issues=[Issue(**i) for i in summary["issues"]],
    )
    if trajectory.check_status == "passed":
        issues = validate_trajectory(project, trajectory)
        if issues:
            raise ValueError(
                "Imported trajectory failed independent validation: " + issues[0].code
            )
    return project, trajectory

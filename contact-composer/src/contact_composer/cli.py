"""Headless commands and a loopback-only editor service."""

import argparse
import json
from pathlib import Path

from .examples import NAMES, example
from .export import load_trajectory, write_bundle
from .project import parse_project, save_project
from .simulation import replay
from .trajectory import generate


def main(argv=None):
    parser = argparse.ArgumentParser(prog="contact-composer")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "solve", "replay"):
        command = sub.add_parser(name)
        command.add_argument("project", type=Path)
        if name != "validate":
            command.add_argument("--output", type=Path, required=True)
        if name == "replay":
            command.add_argument("--trajectory", type=Path, required=True)
    command = sub.add_parser("example")
    command.add_argument("name", choices=NAMES)
    command.add_argument("--output", type=Path, required=True)
    command = sub.add_parser("serve")
    command.add_argument("--port", type=int, default=8765)
    command.add_argument("--runs", type=Path, default=Path("runs"))
    args = parser.parse_args(argv)
    try:
        if args.command == "serve":
            import uvicorn

            from .service import create_app

            uvicorn.run(create_app(args.runs), host="127.0.0.1", port=args.port)
            return 0
        if args.command == "example":
            if args.output.exists():
                raise FileExistsError("Output already exists")
            save_project(example(args.name), args.output)
            print(json.dumps({"output": str(args.output)}))
            return 0
        project = parse_project(args.project.read_text(encoding="utf-8"))
        if args.command == "validate":
            print(
                json.dumps({"input_status": "valid", "project_hash": project.digest()})
            )
            return 0
        if args.output.exists():
            raise FileExistsError("Output already exists")
        if args.command == "solve":
            result = generate(project)
            passed = result.check_status == "passed"
        else:
            _, trajectory = load_trajectory(args.trajectory, project)
            result = replay(project, trajectory)
            passed = result.status == "passed"
        write_bundle(project, result, args.output)
        print(json.dumps(result.summary(), allow_nan=False))
        return 0 if passed else 2
    except (ValueError, OSError, KeyError) as error:
        print(json.dumps({"status": "error", "message": str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

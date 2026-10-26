"""M09: loopback API, immutable snapshots, cancellable process-isolated jobs."""

import io
import json
import multiprocessing as mp
import threading
import time
import uuid
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from queue import Empty
from urllib.parse import urlparse

import numpy as np
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .examples import NAMES, example
from .export import load_trajectory, write_bundle
from .model import RobotModel
from .project import parse_project, standing_project
from .simulation import replay
from .trajectory import generate


def worker(document, kind, plan_path, output, events, cancel):
    try:
        project = parse_project(document)

        def progress(fraction, message):
            events.put({"progress": fraction, "message": message})

        if kind == "solve":
            result = generate(project, progress, cancel.is_set)
        else:
            _, trajectory = load_trajectory(plan_path, project)
            result = replay(project, trajectory, progress, cancel.is_set)
        write_bundle(project, result, output)
        events.put(
            {
                "status": "cancelled" if cancel.is_set() else "completed",
                "progress": 1.0,
                "summary": result.summary(),
            }
        )
    except Exception as error:
        events.put(
            {
                "status": "failed",
                "message": str(error),
                "error_type": type(error).__name__,
            }
        )


class Jobs:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.context = mp.get_context("spawn")
        self.items = {}
        self.lock = threading.RLock()

    def refresh(self, item):
        while True:
            try:
                item["public"].update(item["queue"].get_nowait())
                item["public"]["sequence"] += 1
            except Empty:
                break
        process = item["process"]
        if item["public"]["status"] == "running":
            elapsed = time.monotonic() - item["start"]
            forced = (
                item.get("cancel_time") is not None
                and time.monotonic() - item["cancel_time"] > 3
            )
            if elapsed > item["timeout"] or forced:
                process.terminate()
                process.join(2)
                item["public"].update(
                    status="cancelled" if forced else "failed",
                    message="Worker stopped after cancellation"
                    if forced
                    else "Worker time budget exceeded",
                )
            elif process.exitcode is not None:
                # A final queue message can arrive immediately after process exit.
                try:
                    item["public"].update(item["queue"].get(timeout=0.1))
                except Empty:
                    item["public"].update(
                        status="failed", message=f"Worker exited: {process.exitcode}"
                    )
        if item["public"]["status"] != "running":
            process.join(0.1)

    def get(self, key):
        with self.lock:
            if key not in self.items:
                raise HTTPException(404, "Unknown job")
            item = self.items[key]
            self.refresh(item)
            return item

    def submit(self, project, kind, plan=None):
        with self.lock:
            for item in self.items.values():
                self.refresh(item)
            if any(i["public"]["status"] == "running" for i in self.items.values()):
                raise HTTPException(409, "Another job is running")
            if len(self.items) >= 64:
                raise HTTPException(
                    429, "Session job limit reached; restart the service"
                )
            key = uuid.uuid4().hex
            events = self.context.Queue()
            cancel = self.context.Event()
            output = self.root / key
            process = self.context.Process(
                target=worker,
                args=(
                    project.canonical(),
                    kind,
                    str(plan) if plan else None,
                    str(output),
                    events,
                    cancel,
                ),
                daemon=True,
            )
            public = {
                "id": key,
                "kind": kind,
                "status": "running",
                "progress": 0.0,
                "message": "Starting worker",
                "project_hash": project.digest(),
                "revision": project.revision,
                "sequence": 0,
            }
            self.items[key] = {
                "public": public,
                "process": process,
                "queue": events,
                "cancel": cancel,
                "output": output,
                "start": time.monotonic(),
                "timeout": project.settings.planning.timeout_s + 90,
            }
            process.start()
            return public.copy()

    def close(self):
        for item in self.items.values():
            item["cancel"].set()
            item["process"].join(0.5)
            if item["process"].is_alive():
                item["process"].terminate()
                item["process"].join(2)
            item["queue"].close()


def create_app(root="runs", frontend=None):
    jobs = Jobs(root)

    @asynccontextmanager
    async def lifespan(app):
        yield
        jobs.close()

    app = FastAPI(title="Contact Composer", lifespan=lifespan)
    app.state.jobs = jobs
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @app.middleware("http")
    async def local_requests(request, call_next):
        origin = request.headers.get("origin")
        if origin and urlparse(origin).hostname not in ("127.0.0.1", "localhost"):
            return JSONResponse(
                {"detail": "Only local browser origins are allowed"}, 403
            )
        if request.method == "POST":
            if (
                request.headers.get("content-type", "").split(";")[0]
                != "application/json"
            ):
                return JSONResponse({"detail": "Expected application/json"}, 415)
            chunks = []
            length = 0
            async for chunk in request.stream():
                length += len(chunk)
                if length > 1_000_000:
                    return JSONResponse({"detail": "Request exceeds 1 MB"}, 413)
                chunks.append(chunk)
            request._body = b"".join(chunks)
        return await call_next(request)

    async def document(request):
        try:
            return parse_project((await request.body()).decode("utf-8"))
        except (ValueError, UnicodeError) as error:
            raise HTTPException(422, str(error)) from error

    @app.get("/api/models")
    def models():
        return RobotModel(standing_project()).manifest()

    @app.get("/api/examples")
    def examples():
        return list(NAMES)

    @app.get("/api/examples/{name}")
    def get_example(name: str):
        try:
            return example(name).model_dump(mode="json")
        except KeyError:
            raise HTTPException(404, "Unknown example")

    @app.post("/api/validate")
    async def validate(request: Request):
        project = await document(request)
        return {
            "input_status": "valid",
            "project_hash": project.digest(),
            "revision": project.revision,
        }

    @app.post("/api/solve", status_code=202)
    async def solve(request: Request):
        return jobs.submit(await document(request), "solve")

    @app.post("/api/replay/{plan_id}", status_code=202)
    async def run_replay(plan_id: str, request: Request):
        project = await document(request)
        item = jobs.get(plan_id)
        summary = item["public"].get("summary", {})
        if item["public"]["kind"] != "solve" or summary.get("check_status") != "passed":
            raise HTTPException(409, "A passed planning result is required")
        if project.digest() != item["public"]["project_hash"]:
            raise HTTPException(409, "STALE_RESULT: project changed")
        return jobs.submit(project, "replay", item["output"])

    @app.get("/api/jobs/{key}")
    def status(key: str):
        return jobs.get(key)["public"].copy()

    @app.delete("/api/jobs/{key}")
    def cancel(key: str):
        item = jobs.get(key)
        if item["public"]["status"] == "running":
            item["cancel"].set()
            item["cancel_time"] = time.monotonic()
            item["public"]["message"] = "Cancellation requested"
        return item["public"].copy()

    def result_path(key):
        item = jobs.get(key)
        if (
            item["public"]["status"] not in ("completed", "cancelled")
            or not (item["output"] / "manifest.json").exists()
        ):
            raise HTTPException(409, "Result not available")
        return item["output"]

    @app.get("/api/results/{key}")
    def result(key: str):
        path = result_path(key)
        with np.load(path / "arrays.npz", allow_pickle=False) as data:
            arrays = {k: data[k].tolist() for k in data.files}
        return {
            "summary": json.loads((path / "summary.json").read_text()),
            "arrays": arrays,
        }

    @app.get("/api/results/{key}/download")
    def download(key: str):
        path = result_path(key)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for name in (
                "manifest.json",
                "project.json",
                "summary.json",
                "arrays.npz",
                "model.xml",
            ):
                archive.write(path / name, name)
        return Response(
            buffer.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="contact-composer-{key}.zip"'
            },
        )

    assets = (
        Path(frontend)
        if frontend
        else Path(__file__).resolve().parents[2] / "frontend" / "dist"
    )
    if assets.is_dir():
        app.mount("/", StaticFiles(directory=assets, html=True), name="editor")
    return app

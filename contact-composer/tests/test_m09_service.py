import time

import pytest
from fastapi.testclient import TestClient

from contact_composer.project import standing_project
from contact_composer.service import create_app


def wait(client, key):
    deadline = time.monotonic() + 40
    while time.monotonic() < deadline:
        result = client.get("/api/jobs/" + key).json()
        if result["status"] != "running":
            return result
        time.sleep(0.1)
    pytest.fail("Worker timeout")


def test_validate_origins_payloads_and_unknown_jobs(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        assert client.get("/api/models").json()["version"] == "1.0"
        assert (
            client.post(
                "/api/validate", json=standing_project().model_dump()
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/validate", json={}, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert client.post("/api/validate", json={}).status_code == 422
        assert (
            client.post(
                "/api/validate",
                content="a" * 1_000_001,
                headers={"Content-Type": "application/json"},
            ).status_code
            == 413
        )
        assert client.get("/api/jobs/missing").status_code == 404


def test_process_solve_replay_export_and_stale_revision(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        project = standing_project(40).model_dump(mode="json")
        response = client.post("/api/solve", json=project)
        assert response.status_code == 202, response.text
        key = response.json()["id"]
        result = wait(client, key)
        assert result["summary"]["check_status"] == "passed", result
        assert client.get("/api/results/" + key).json()["arrays"]["q"]
        assert client.get("/api/results/" + key + "/download").content[:2] == b"PK"
        project["revision"] = 1
        assert client.post("/api/replay/" + key, json=project).status_code == 409
        project["revision"] = 0
        replay_key = client.post("/api/replay/" + key, json=project).json()["id"]
        assert wait(client, replay_key)["summary"]["status"] == "passed"


def test_cancel_process_job(tmp_path):
    with TestClient(create_app(tmp_path)) as client:
        key = client.post("/api/solve", json=standing_project(400).model_dump()).json()[
            "id"
        ]
        assert (
            client.post("/api/solve", json=standing_project().model_dump()).status_code
            == 409
        )
        client.delete("/api/jobs/" + key)
        assert wait(client, key)["status"] == "cancelled"

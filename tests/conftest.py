import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from visionlabel.api import create_app
from visionlabel.domain import uid
from visionlabel.fixtures import png_bytes
from visionlabel.service import Service


@pytest.fixture
def environment(tmp_path):
    root = tmp_path / "server"
    service = Service(root)
    service.bootstrap("admin", "a-strong-test-password")
    service.close()
    with TestClient(create_app(root)) as client:
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "a-strong-test-password"}
        )
        client.headers["Authorization"] = "Bearer " + login.json()["token"]
        yield client, client.app.state.service, root


def project(client, task="detection"):
    response = client.post(
        "/api/v1/projects",
        json={
            "name": "Synthetic inspection",
            "slug": "project-" + uid(),
            "task_type": task,
            "initial_classes": ["part", "defect", "background"],
        },
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 201, response.text
    return response.json()


def import_files(client, root: Path, project_id, count=1):
    paths = []
    for index in range(count):
        name = f"sample-{index:04d}.png"
        (root / "inbox" / name).write_bytes(png_bytes(index, 100, 200))
        paths.append(name)
    response = client.post(
        f"/api/v1/projects/{project_id}/imports",
        json={"relative_paths": paths},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)  # Job completion polling, not race orchestration.
    assert job["state"] == "succeeded", job
    assert all(item["outcome"] == "imported" for item in job["result"]["items"]), job
    return client.get(f"/api/v1/projects/{project_id}/images?limit=500").json()["items"]


def claim(client, image_id):
    response = client.post(
        f"/api/v1/images/{image_id}/claim",
        json={"mode": "edit", "client_instance_id": uid()},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 201, response.text
    lease = response.json()
    return {
        "X-Claim-ID": lease["claim_id"],
        "X-Claim-Token": lease["claim_token"],
        "X-Claim-Generation": str(lease["generation"]),
    }


def save_body(project, revision=0, state_revision=0):
    return {
        "expected_revision": revision,
        "expected_state_revision": state_revision,
        "class_schema_id": project["active_schema_id"],
        "content": {
            "verified_empty": False,
            "image_labels": [],
            "shapes": [
                {
                    "id": uid(),
                    "type": "rectangle",
                    "class_id": project["schema"]["entries"][0]["class_id"],
                    "x1": 10,
                    "y1": 20,
                    "x2": 50,
                    "y2": 100,
                    "attributes": {},
                }
            ],
        },
    }

import io
import json
import threading
import time
import zipfile

import pytest
from conftest import claim, import_files, project, save_body
from test_team import create_user, member
from test_working_export import labeled, start, wait

from visionlabel.database import row
from visionlabel.domain import uid


def delete(client, iid, revision=0, state=0, lease=None, key=None):
    return client.request(
        "DELETE",
        f"/api/v1/images/{iid}",
        json={"expected_revision": revision, "expected_state_revision": state},
        headers={"Idempotency-Key": key or uid(), **(lease or {})},
    )


def test_delete_preserves_evidence_shared_asset_and_replays(environment):
    client, srv, root = environment
    proj, other = project(client), project(client)
    image = import_files(client, root, proj["id"])[0]
    shared = import_files(client, root, other["id"])[0]
    iid = image["id"]
    lease = claim(client, iid)
    saved = client.put(
        f"/api/v1/images/{iid}/annotation", json=save_body(proj), headers={**lease, "Idempotency-Key": uid()}
    )
    assert saved.status_code == 200, saved.text
    head = saved.json()
    key = uid()
    response = delete(client, iid, head["revision"], head["state_revision"], lease, key)
    assert response.status_code == 200, response.text
    assert delete(client, iid, head["revision"], head["state_revision"], lease, key).json() == response.json()
    assert delete(client, iid, head["revision"] + 1, head["state_revision"], lease, key).status_code == 409
    assert client.get(f"/api/v1/projects/{proj['id']}/images").json()["items"] == []
    for suffix in ("", "/content", "/annotation", "/reviews", "/revisions/1"):
        assert client.get(f"/api/v1/images/{iid}{suffix}").status_code == 404
    assert client.get(f"/api/v1/images/{shared['id']}/content").status_code == 200
    with srv.db.engine.connect() as conn:
        assert row(conn, "SELECT * FROM annotation_revisions WHERE image_id=?", (iid,))
        assert row(conn, "SELECT COUNT(*) AS n FROM audit_events WHERE action='image.deleted'")["n"] == 1
        asset = row(conn, "SELECT * FROM assets WHERE sha256=?", (image["asset_sha256"],))
        assert (root / "managed" / asset["blob_path"]).exists()
    job = client.post(
        f"/api/v1/projects/{proj['id']}/imports",
        json={"relative_paths": ["sample-0000.png"]},
        headers={"Idempotency-Key": uid()},
    ).json()
    for _ in range(300):
        result = client.get(f"/api/v1/jobs/{job['job_id']}").json()
        if result["state"] in ("succeeded", "failed"):
            break
        time.sleep(0.01)
    assert "IMAGE_DELETED" in str(result)
    assert client.get(f"/api/v1/projects/{proj['id']}/images").json()["items"] == []


def test_delete_requires_current_revision_and_live_claim_token(environment):
    client, _, root = environment
    proj = project(client)
    iid = import_files(client, root, proj["id"])[0]["id"]
    lease = claim(client, iid)
    assert delete(client, iid, revision=1, lease=lease).status_code == 409
    assert delete(client, iid, state=1, lease=lease).status_code == 409
    assert delete(client, iid).status_code == 409
    assert client.get(f"/api/v1/images/{iid}").status_code == 200
    assert delete(client, iid, lease=lease).status_code == 200


@pytest.mark.parametrize("role", ["viewer", "annotator", "reviewer"])
def test_delete_requires_maintainer(environment, role):
    client, srv, root = environment
    proj = project(client)
    iid = import_files(client, root, proj["id"])[0]["id"]
    user = create_user(client)
    assert member(client, proj, user, role).status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    assert delete(client, iid).status_code == 403


def test_delete_without_active_claim_and_rejects_future_saves(environment):
    client, _, root = environment
    proj = project(client)
    iid = import_files(client, root, proj["id"])[0]["id"]
    lease = claim(client, iid)
    assert client.delete(f"/api/v1/images/{iid}/claim", headers=lease).status_code == 204
    assert delete(client, iid).status_code == 200
    assert (
        client.put(
            f"/api/v1/images/{iid}/annotation",
            json=save_body(proj),
            headers={**lease, "Idempotency-Key": uid()},
        ).status_code
        == 404
    )


def test_queued_snapshot_survives_deletion_and_future_export_excludes_image(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=4)
    iid = images[0]["id"]
    gate = threading.Event()
    blocker = srv.pool.submit(gate.wait, 15)
    try:
        old_job = start(client, proj, test_percent=0).json()["job_id"]
        assert delete(client, iid, revision=1, state=1).status_code == 200
    finally:
        gate.set()
        blocker.result()
    assert wait(client, old_job)["state"] == "succeeded"
    old_bytes = client.get(f"/api/v1/working-exports/{old_job}/download").content
    old = json.loads(zipfile.ZipFile(io.BytesIO(old_bytes)).read("manifest.json"))
    assert iid in {i["image_id"] for i in old["items"]}
    new_job = start(client, proj, test_percent=0).json()["job_id"]
    assert wait(client, new_job)["state"] == "succeeded"
    new_bytes = client.get(f"/api/v1/working-exports/{new_job}/download").content
    new = json.loads(zipfile.ZipFile(io.BytesIO(new_bytes)).read("manifest.json"))
    assert len(new["items"]) == 3
    assert iid not in {i["image_id"] for i in new["items"]}
    assert client.get(f"/api/v1/working-exports/{old_job}/download").content == old_bytes

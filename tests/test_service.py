import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from conftest import claim, import_files, project, save_body

from visionlabel.database import row
from visionlabel.domain import Problem, digest, uid
from visionlabel.service import Service, now


def setup_image(environment, task="detection"):
    client, service, root = environment
    proj = project(client, task)
    image = import_files(client, root, proj["id"])[0]
    return client, service, root, proj, image


def test_save_reload_and_idempotency(environment):
    client, service, root, proj, image = setup_image(environment)
    image_id = image["id"]
    lease = claim(client, image_id)
    headers = dict(lease, **{"Idempotency-Key": uid()})
    body = save_body(proj)
    path = f"/api/v1/images/{image_id}/annotation"
    saved = client.put(path, json=body, headers=headers)
    assert saved.status_code == 200, saved.text
    replay = client.put(path, json=body, headers=headers)
    assert replay.json() == saved.json()
    loaded = client.get(path).json()
    assert loaded["revision"] == 1
    assert loaded["annotation"]["shapes"] == body["content"]["shapes"]
    assert loaded["annotation_sha256"] == saved.json()["annotation_sha256"]
    body["content"]["shapes"][0]["x1"] = 11
    assert client.put(path, json=body, headers=headers).status_code == 409
    assert client.put(path, json=body, headers=dict(lease, **{"Idempotency-Key": uid()})).status_code == 409
    assert client.get(path).json() == loaded
    with service.db.engine.connect() as conn:
        revision = row(conn, "SELECT * FROM annotation_revisions WHERE image_id=?", (image_id,))
        raw = service.blobs.read(revision["blob_path"], revision["sha256"])
        assert digest(raw) == loaded["annotation_sha256"]
        audit = row(
            conn, "SELECT * FROM audit_events WHERE action='annotation.saved' AND entity_id=?", (image_id,)
        )
        assert json.loads(audit["detail_json"])["created"] == [body["content"]["shapes"][0]["id"]]


def test_claim_race_only_one_winner(environment):
    client, service, root, proj, image = setup_image(environment)
    user = service.authenticate(client.headers["Authorization"][7:])
    barrier = Barrier(2)

    def race(_):
        barrier.wait()
        try:
            service.claim(user, image["id"], {"mode": "edit", "client_instance_id": uid()}, uid(), uid())
            return 201
        except Problem as exc:
            return exc.status

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(race, range(2))) == [201, 423]


def test_save_race_and_orphans(environment):
    client, service, root, proj, image = setup_image(environment)
    lease = claim(client, image["id"])
    user = service.authenticate(client.headers["Authorization"][7:])
    headers = {
        "id": lease["X-Claim-ID"],
        "token": lease["X-Claim-Token"],
        "generation": lease["X-Claim-Generation"],
    }
    barrier = Barrier(2)
    service.fault = lambda point: barrier.wait() if point == "after_publish" else None

    def race(_):
        try:
            return service.save(user, image["id"], save_body(proj), headers, uid(), uid())["revision"]
        except Problem as exc:
            return exc.status

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(race, range(2))) == [1, 409]
    assert service.annotation(user, image["id"])["revision"] == 1


@pytest.mark.parametrize("boundary", ["before_publish", "after_publish", "before_commit", "after_commit"])
def test_crash_boundaries(environment, boundary):
    client, service, root, proj, image = setup_image(environment)
    lease = claim(client, image["id"])
    user = service.authenticate(client.headers["Authorization"][7:])
    headers = {
        "id": lease["X-Claim-ID"],
        "token": lease["X-Claim-Token"],
        "generation": lease["X-Claim-Generation"],
    }
    request_key = uid()
    body = save_body(proj)

    def crash(point):
        if point == boundary:
            raise RuntimeError("simulated process failure")

    service.fault = crash
    with pytest.raises(RuntimeError):
        service.save(user, image["id"], body, headers, request_key, uid())
    service.fault = lambda _: None
    assert service.annotation(user, image["id"])["revision"] == (1 if boundary == "after_commit" else 0)
    if boundary == "after_commit":
        # A replay must succeed even after the lease expires.
        with service.db.transaction() as conn:
            conn.exec_driver_sql("UPDATE task_claims SET expires_at=?", (now(),))
        assert service.save(user, image["id"], body, headers, request_key, uid())["revision"] == 1


def test_expired_lease_and_restart(environment):
    client, service, root, proj, image = setup_image(environment)
    lease = claim(client, image["id"])
    with service.db.transaction() as conn:
        conn.exec_driver_sql("UPDATE task_claims SET expires_at=?", (now(),))
    response = client.put(
        f"/api/v1/images/{image['id']}/annotation",
        json=save_body(proj),
        headers=dict(lease, **{"Idempotency-Key": uid()}),
    )
    assert response.status_code == 409
    new = claim(client, image["id"])
    assert int(new["X-Claim-Generation"]) > int(lease["X-Claim-Generation"])
    assert client.post(f"/api/v1/images/{image['id']}/claim/heartbeat", headers=lease).status_code == 409
    service.close()
    replacement = Service(root)
    client.app.state.service = replacement
    assert client.post(f"/api/v1/images/{image['id']}/claim/heartbeat", headers=new).status_code == 409


def test_classification_persists(environment):
    client, service, root, proj, image = setup_image(environment, "classification")
    lease = claim(client, image["id"])
    body = save_body(proj)
    body["content"] = {
        "verified_empty": False,
        "image_labels": [proj["schema"]["entries"][1]["class_id"]],
        "shapes": [],
    }
    response = client.put(
        f"/api/v1/images/{image['id']}/annotation",
        json=body,
        headers=dict(lease, **{"Idempotency-Key": uid()}),
    )
    assert response.status_code == 200, response.text
    assert (
        client.get(f"/api/v1/images/{image['id']}/annotation").json()["annotation"]["image_labels"]
        == body["content"]["image_labels"]
    )


def test_import_100_dedup_and_invalid(environment):
    client, service, root = environment
    proj = project(client)
    images = import_files(client, root, proj["id"], 100)
    assert len(images) == 100
    page = client.get(f"/api/v1/projects/{proj['id']}/images?limit=17").json()
    assert len(page["items"]) == 17 and page["next_cursor"]
    second = client.get(f"/api/v1/projects/{proj['id']}/images?limit=17&cursor=" + page["next_cursor"]).json()
    assert not ({x["id"] for x in page["items"]} & {x["id"] for x in second["items"]})
    bad = client.get(f"/api/v1/projects/{proj['id']}/images?search=changed&cursor=" + page["next_cursor"])
    assert bad.status_code == 400
    user = service.authenticate(client.headers["Authorization"][7:])
    duplicate = service.ingest(user, proj["id"], next(iter_job(service)), "sample-0000.png", True, uid())
    assert duplicate["outcome"] == "duplicate"
    for relative in ["../secret.png", "C:/secret.png", "//host/share/x.png", "CON.png"]:
        with pytest.raises(Problem):
            service.ingest(user, proj["id"], uid(), relative, True, uid())


def iter_job(service):
    with service.db.engine.connect() as conn:
        yield row(conn, "SELECT id FROM jobs LIMIT 1")["id"]


def test_auth_unknown_fields_and_missing_claim(environment):
    client, service, root, proj, image = setup_image(environment)
    body = save_body(proj)
    assert client.put(f"/api/v1/images/{image['id']}/annotation", json=body).status_code == 422
    body["force"] = True
    assert client.put(f"/api/v1/images/{image['id']}/annotation", json=body).status_code == 422
    headers = client.headers.pop("Authorization")
    assert client.get(f"/api/v1/images/{image['id']}/content").status_code == 401
    client.headers["Authorization"] = headers


def test_missing_blob_is_not_empty_annotation(environment):
    client, service, root, proj, image = setup_image(environment)
    lease = claim(client, image["id"])
    path = f"/api/v1/images/{image['id']}/annotation"
    assert (
        client.put(path, json=save_body(proj), headers=dict(lease, **{"Idempotency-Key": uid()})).status_code
        == 200
    )
    with service.db.engine.connect() as conn:
        revision = row(conn, "SELECT blob_path FROM annotation_revisions WHERE image_id=?", (image["id"],))
    (service.blobs.root / revision["blob_path"]).unlink()
    assert client.get(path).status_code == 503

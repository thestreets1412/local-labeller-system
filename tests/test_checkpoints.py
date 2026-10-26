import json

import pytest
from conftest import claim, project, save_body
from test_working_export import labeled, start, wait

from visionlabel.domain import canonical, uid
from visionlabel.fixtures import png_bytes
from visionlabel.operations import backup, restore, verify_backup


def preview(client, proj, label, kind="checkpoint", **extra):
    response = client.post(
        f"/api/v1/projects/{proj['id']}/dataset-preview",
        json={"kind": kind, "label": label, "message": "Dataset " + label, **extra},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 200, response.text
    return response.json()


def apply_preview(client, proj, candidate):
    response = client.post(
        f"/api/v1/projects/{proj['id']}/dataset-operations/{candidate['operation_id']}/apply",
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 202, response.text
    return wait(client, response.json()["job_id"])


def checkpoint(client, proj, label):
    job = apply_preview(client, proj, preview(client, proj, label))
    assert job["state"] == "succeeded", job
    return job["result"]["checkpoint"]


def edits(proj):
    return [{k: e[k] for k in ("class_id", "display_name", "active")} for e in proj["schema"]["entries"]]


@pytest.mark.parametrize("task", ["detection", "segmentation", "classification"])
def test_checkpoint_schema_restore_export_journey(environment, task):
    client, srv, root = environment
    proj, images = labeled(client, root, task, count=3)
    pid, iid = proj["id"], images[0]["id"]
    original = client.get(f"/api/v1/images/{iid}/annotation").json()
    v1 = checkpoint(client, proj, "v1")
    frozen = srv.blobs.read(v1["blob_path"], v1["sha256"])
    # A later import must not enter v1 or survive a v1 restore.
    (root / "inbox" / "later.png").write_bytes(png_bytes(999, 100, 200))
    imported = client.post(
        f"/api/v1/projects/{pid}/imports",
        json={"relative_paths": ["later.png"]},
        headers={"Idempotency-Key": uid()},
    )
    assert wait(client, imported.json()["job_id"])["state"] == "succeeded"
    v2 = checkpoint(client, proj, "v2")
    assert client.get(f"/api/v1/projects/{pid}/checkpoints/{v2['id']}").json()["total"] == 4
    # Remove an old image, then change the class identity/name mapping of survivors.
    removed = client.request(
        "DELETE",
        f"/api/v1/images/{iid}",
        json={"expected_revision": 1, "expected_state_revision": 1},
        headers={"Idempotency-Key": uid()},
    )
    assert removed.status_code == 200, removed.text
    classes = edits(proj)
    classes[0]["active"] = False
    classes[1]["display_name"] = "必要 / defect"
    candidate = preview(
        client,
        proj,
        "v3",
        "schema",
        classes=classes,
        mapping={classes[0]["class_id"]: classes[1]["class_id"]},
    )
    migrated = apply_preview(client, proj, candidate)
    assert migrated["state"] == "succeeded", migrated
    v3 = migrated["result"]["checkpoint"]
    current = client.get(f"/api/v1/projects/{pid}").json()
    assert current["active_schema_id"] != proj["active_schema_id"]
    assert current["schema"]["entries"][0]["active"] is False
    assert srv.blobs.read(v1["blob_path"], v1["sha256"]) == frozen
    historical = client.get(f"/api/v1/projects/{pid}/checkpoints/{v1['id']}/images/{iid}")
    assert historical.status_code == 200
    assert historical.json()["annotation"] == original["annotation"]
    assert client.get(f"/api/v1/images/{iid}").status_code == 404
    exported = []
    for version in (v1, v2, v3, v1):
        response = start(client, proj, checkpoint_id=version["id"], test_percent=0)
        assert response.status_code == 202, response.text
        job = wait(client, response.json()["job_id"])
        assert job["state"] == "succeeded", job
        exported.append(job["result"]["sha256"])
    assert exported[0] == exported[3]
    restored = apply_preview(
        client, proj, preview(client, proj, "return-v1", "restore", checkpoint_id=v1["id"])
    )
    assert restored["state"] == "succeeded", restored
    result = restored["result"]
    assert result["checkpoint"]["restored_from_id"] == v1["id"]
    assert result["safety_checkpoint"] is not None
    active = client.get(f"/api/v1/projects/{pid}/images").json()["items"]
    assert {i["id"] for i in active} == {i["id"] for i in images}
    head = client.get(f"/api/v1/images/{iid}/annotation").json()
    assert head["revision"] > original["revision"] and head["status"] == "IN_PROGRESS"
    assert {k: head["annotation"][k] for k in ("shapes", "image_labels", "verified_empty")} == {
        k: original["annotation"][k] for k in ("shapes", "image_labels", "verified_empty")
    }
    again = apply_preview(client, proj, preview(client, proj, "return-v3", "restore", checkpoint_id=v3["id"]))
    assert again["state"] == "succeeded", again
    assert client.get(f"/api/v1/images/{iid}").status_code == 404
    assert srv.blobs.read(v1["blob_path"], v1["sha256"]) == frozen
    # History pages contain all named versions and immutable safety checkpoints.
    page = client.get(f"/api/v1/projects/{pid}/checkpoints?limit=2").json()
    page2 = client.get(f"/api/v1/projects/{pid}/checkpoints?limit=2&before={page['next_before']}").json()
    assert not {c["id"] for c in page["items"]} & {c["id"] for c in page2["items"]}


def test_remove_last_class_annotation_is_not_verified_empty(environment):
    client, _, root = environment
    proj, images = labeled(client, root, count=1)
    classes = edits(proj)
    classes[0]["active"] = False
    invalid = client.post(
        f"/api/v1/projects/{proj['id']}/dataset-preview",
        json={"kind": "schema", "label": "bad", "message": "bad", "classes": classes},
        headers={"Idempotency-Key": uid()},
    )
    assert invalid.json()["error"]["code"] == "CLASS_IN_USE"
    job = apply_preview(
        client,
        proj,
        preview(client, proj, "removed", "schema", classes=classes, mapping={classes[0]["class_id"]: None}),
    )
    assert job["state"] == "succeeded", job
    head = client.get(f"/api/v1/images/{images[0]['id']}/annotation").json()
    assert head["status"] == "UNLABELED" and not head["annotation"]["verified_empty"]
    assert head["annotation"]["shapes"] == []


def test_stale_preview_active_claim_and_retry(environment):
    client, _, root = environment
    proj, images = labeled(client, root, count=1)
    iid = images[0]["id"]
    v1 = checkpoint(client, proj, "v1")
    candidate = preview(client, proj, "restore", "restore", checkpoint_id=v1["id"])
    lease = claim(client, iid)
    failed = apply_preview(client, proj, candidate)
    assert failed["error"]["code"] == "DATASET_CLAIMED"
    body = save_body(proj, 1, 1)
    assert (
        client.put(
            f"/api/v1/images/{iid}/annotation", json=body, headers=lease | {"Idempotency-Key": uid()}
        ).status_code
        == 200
    )
    client.delete(f"/api/v1/images/{iid}/claim", headers=lease)
    failed = apply_preview(client, proj, candidate)
    assert failed["error"]["code"] == "REVISION_CONFLICT"
    head = client.get(f"/api/v1/images/{iid}/annotation").json()
    assert head["revision"] == 2


@pytest.mark.parametrize("fault", ["dataset_after_publish", "dataset_before_commit", "dataset_after_commit"])
def test_atomic_fault_recovery_and_idempotent_result(environment, fault):
    client, srv, root = environment
    proj, images = labeled(client, root, count=2)
    v1 = checkpoint(client, proj, "v1")
    candidate = preview(client, proj, "restore", "restore", checkpoint_id=v1["id"])

    def fail(point):
        if point == fault:
            raise OSError("Injected interruption")

    srv.fault = fail
    result = apply_preview(client, proj, candidate)
    assert result["state"] == "failed"
    revisions = [client.get(f"/api/v1/images/{i['id']}/annotation").json()["revision"] for i in images]
    assert revisions == ([2, 2] if fault == "dataset_after_commit" else [1, 1])
    srv.fault = lambda _: None
    retried = apply_preview(client, proj, candidate)
    assert retried["state"] == "succeeded", retried
    replay = apply_preview(client, proj, candidate)
    assert replay["result"] == retried["result"]
    assert [client.get(f"/api/v1/images/{i['id']}/annotation").json()["revision"] for i in images] == [2, 2]


def test_checkpoint_frozen_candidate_empty_and_corruption(environment):
    client, srv, root = environment
    empty = project(client)
    assert checkpoint(client, empty, "empty")["sha256"]
    proj, images = labeled(client, root, count=1)
    candidate = preview(client, proj, "frozen")
    iid = images[0]["id"]
    lease = claim(client, iid)
    client.put(
        f"/api/v1/images/{iid}/annotation",
        json=save_body(proj, 1, 1),
        headers=lease | {"Idempotency-Key": uid()},
    )
    client.delete(f"/api/v1/images/{iid}/claim", headers=lease)
    job = apply_preview(client, proj, candidate)
    assert job["state"] == "succeeded"
    version = job["result"]["checkpoint"]
    record = client.get(f"/api/v1/projects/{proj['id']}/checkpoints/{version['id']}").json()["items"][0]
    assert record["current_revision"] == 1
    bad = preview(client, proj, "corrupt", "restore", checkpoint_id=version["id"])
    (srv.blobs.root / record["asset_path"]).write_bytes(b"corrupt")
    result = apply_preview(client, proj, bad)
    assert result["error"]["code"] == "CORRUPT_BLOB"
    assert client.get(f"/api/v1/images/{iid}/annotation").json()["revision"] == 2


def test_checkpoint_backup_contains_operation_and_manifest(environment, tmp_path):
    client, srv, root = environment
    proj, _ = labeled(client, root, count=1)
    version = checkpoint(client, proj, "保存")
    destination = tmp_path / "backup"
    srv.close()
    backup(root, destination)
    verify_backup(destination)
    restored = tmp_path / "restored"
    restore(destination, restored)
    assert (restored / "managed" / version["blob_path"]).read_bytes() == srv.blobs.read(
        version["blob_path"], version["sha256"]
    )


def test_preview_authorization_scoping_and_label_conflict(environment):
    client, srv, root = environment
    proj, _ = labeled(client, root, count=1)
    other = project(client)
    version = checkpoint(client, proj, "v1")
    assert client.get(f"/api/v1/projects/{other['id']}/checkpoints/{version['id']}").status_code == 404
    body = {"kind": "checkpoint", "label": "v1", "message": "duplicate"}
    response = client.post(
        f"/api/v1/projects/{proj['id']}/dataset-preview", json=body, headers={"Idempotency-Key": uid()}
    )
    assert response.json()["error"]["code"] == "LABEL_EXISTS"
    # Even the administrator needs a project mutation role.
    with srv.db.transaction() as conn:
        conn.exec_driver_sql("UPDATE project_members SET role='viewer' WHERE project_id=?", (proj["id"],))
    body["label"] = "v2"
    response = client.post(
        f"/api/v1/projects/{proj['id']}/dataset-preview", json=body, headers={"Idempotency-Key": uid()}
    )
    assert response.status_code == 403


def test_manifest_golden_fixture():
    from pathlib import Path

    path = Path(__file__).parent / "fixtures/checkpoints/empty.json"
    expected = path.read_bytes()
    from visionlabel.checkpoint_domain import checkpoint_manifest

    document = checkpoint_manifest(
        "project-1", "detection", {"id": "schema-1", "sha256": "abc", "blob_path": "schemas/one.json"}, []
    )
    assert canonical(document) == expected.rstrip(b"\n")
    assert json.loads(expected)["approved_release"] is False


def test_pending_cancel_before_commit_and_after_commit(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=1)
    first = checkpoint(client, proj, "first")
    candidate = preview(client, proj, "restore", "restore", checkpoint_id=first["id"])
    pid = proj["id"]
    pending = client.get(f"/api/v1/projects/{pid}/dataset-operations").json()["items"]
    assert pending[0]["operation_id"] == candidate["operation_id"]

    # Cancellation races after durable files, but before the atomic transaction.
    def cancel(point):
        if point == "dataset_after_publish":
            response = client.delete(f"/api/v1/projects/{pid}/dataset-operations/{candidate['operation_id']}")
            assert response.json()["cancelled"]

    srv.fault = cancel
    job = apply_preview(client, proj, candidate)
    assert job["error"]["code"] == "OPERATION_CANCELLED"
    assert client.get(f"/api/v1/images/{images[0]['id']}/annotation").json()["revision"] == 1
    srv.fault = lambda _: None
    assert not client.get(f"/api/v1/projects/{pid}/dataset-operations").json()["items"]
    candidate = preview(client, proj, "second")
    assert apply_preview(client, proj, candidate)["state"] == "succeeded"
    assert not client.delete(f"/api/v1/projects/{pid}/dataset-operations/{candidate['operation_id']}").json()[
        "cancelled"
    ]


def test_new_class_rename_reactivate_and_indices_never_reused(environment):
    client, _, root = environment
    proj, _ = labeled(client, root, count=1)
    v1 = checkpoint(client, proj, "v1")
    classes = edits(proj)
    classes[0]["display_name"] = "Renamed"
    classes[1]["active"] = False
    classes.append({"display_name": "New", "active": True})
    job = apply_preview(client, proj, preview(client, proj, "new", "schema", classes=classes))
    assert job["state"] == "succeeded", job
    current = client.get(f"/api/v1/projects/{proj['id']}").json()
    assert current["schema"]["entries"][0]["class_id"] == proj["schema"]["entries"][0]["class_id"]
    assert current["schema"]["entries"][-1]["export_index"] == 3
    restored = apply_preview(client, proj, preview(client, proj, "old", "restore", checkpoint_id=v1["id"]))
    assert restored["state"] == "succeeded"
    classes = edits(proj) + [{"display_name": "Another", "active": True}]
    job = apply_preview(client, proj, preview(client, proj, "another", "schema", classes=classes))
    assert job["state"] == "succeeded", job
    current = client.get(f"/api/v1/projects/{proj['id']}").json()
    assert current["schema"]["entries"][-1]["export_index"] == 4
    assert current["schema"]["entries"][-1]["class_id"] != proj["schema"]["entries"][0]["class_id"]


def test_restore_does_not_resurrect_review_and_diff_marks_review_only(environment):
    from test_review import decision_body, enable_solo, mutation, review_claim

    client, _, root = environment
    proj, images = labeled(client, root, count=1)
    iid, pid = images[0]["id"], proj["id"]
    v1 = checkpoint(client, proj, "before-review")
    enable_solo(client, proj)
    lease = review_claim(client, iid)
    assert (
        mutation(client, "POST", f"/images/{iid}/reviews", decision_body(client, iid), lease).status_code
        == 201
    )
    v2 = checkpoint(client, proj, "reviewed")
    diff = client.get(f"/api/v1/projects/{pid}/checkpoints/{v1['id']}/diff?other={v2['id']}").json()
    assert diff["review_only"] == [iid] and not diff["changed_annotations"]
    job = apply_preview(client, proj, preview(client, proj, "restored", "restore", checkpoint_id=v2["id"]))
    assert job["state"] == "succeeded", job
    assert client.get(f"/api/v1/images/{iid}/annotation").json()["status"] == "IN_PROGRESS"
    assert all(not r["applicable"] for r in client.get(f"/api/v1/images/{iid}/reviews").json()["items"])
    historical = client.get(f"/api/v1/projects/{pid}/checkpoints/{v2['id']}").json()
    assert historical["review_counts"] == {"REVIEWED_PASS": 1}


def test_concurrent_save_before_commit_aborts_entire_restore(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=2)
    v1 = checkpoint(client, proj, "v1")
    candidate = preview(client, proj, "restored", "restore", checkpoint_id=v1["id"])
    iid = images[0]["id"]

    def save_between(point):
        if point == "dataset_after_publish":
            lease = claim(client, iid)
            response = client.put(
                f"/api/v1/images/{iid}/annotation",
                json=save_body(proj, 1, 1),
                headers=lease | {"Idempotency-Key": uid()},
            )
            assert response.status_code == 200
            client.delete(f"/api/v1/images/{iid}/claim", headers=lease)

    srv.fault = save_between
    job = apply_preview(client, proj, candidate)
    srv.fault = lambda _: None
    assert job["error"]["code"] == "REVISION_CONFLICT"
    assert [client.get(f"/api/v1/images/{i['id']}/annotation").json()["revision"] for i in images] == [2, 1]
    assert len(client.get(f"/api/v1/projects/{proj['id']}/checkpoints").json()["items"]) == 1


def test_export_confirmation_bound_to_checkpoint_and_source_options(environment):
    client, _, root = environment
    proj, _ = labeled(client, root, count=3)
    v1, v2 = checkpoint(client, proj, "v1"), checkpoint(client, proj, "v2")
    url = f"/api/v1/projects/{proj['id']}/working-exports"
    response = client.post(url, json={"checkpoint_id": v1["id"]}, headers={"Idempotency-Key": uid()})
    token = response.json()["error"]["details"]["confirmation"]
    response = client.post(
        url, json={"checkpoint_id": v2["id"], "confirmation": token}, headers={"Idempotency-Key": uid()}
    )
    assert response.json()["error"]["code"] == "INVALID_CONFIRMATION"


def test_restart_preserves_pending_preview_and_retries(environment):
    from visionlabel import checkpoints
    from visionlabel.database import row
    from visionlabel.service import Service

    client, srv, root = environment
    proj, _ = labeled(client, root, count=1)
    candidate = preview(client, proj, "after-restart")
    srv.close()
    reopened = Service(root)
    try:
        with reopened.db.engine.connect() as conn:
            user = row(conn, "SELECT * FROM users WHERE username='admin'")
        assert (
            checkpoints.pending(reopened, user, proj["id"])["items"][0]["operation_id"]
            == candidate["operation_id"]
        )
        result = checkpoints.apply(reopened, user, proj["id"], candidate["operation_id"], uid())
        assert result["checkpoint"]["label"] == "after-restart"
    finally:
        reopened.close()


def test_pre_phase10_backup_remains_restorable(tmp_path, monkeypatch):
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    import visionlabel.database as database_module
    from visionlabel.database import Database
    from visionlabel.service import Service

    def migrate_old(db):
        config = Config()
        config.set_main_option("script_location", str(Path(database_module.__file__).parent / "migrations"))
        with db.engine.connect() as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.commit()
            config.attributes["connection"] = conn
            command.upgrade(config, "0007")
            conn.commit()

    root = tmp_path / "old"
    with monkeypatch.context() as patch:
        patch.setattr(Database, "migrate", migrate_old)
        service = Service(root)
        service.bootstrap("old", "a-long-backup-password")
        service.close()
    backup(root, tmp_path / "backup")
    verify_backup(tmp_path / "backup")
    restore(tmp_path / "backup", tmp_path / "restored")
    service = Service(tmp_path / "restored")
    try:
        with service.db.engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == "0008"
            assert conn.exec_driver_sql("SELECT count(*) FROM dataset_checkpoints").scalar() == 0
    finally:
        service.close()

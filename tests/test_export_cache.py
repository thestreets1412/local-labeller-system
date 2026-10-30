import json

from test_working_export import labeled, start, wait

from visionlabel.domain import uid


def prepared(environment):
    client, srv, root = environment
    proj, _ = labeled(client, root, count=3)
    job_id = start(client, proj).json()["job_id"]
    job = wait(client, job_id)
    assert job["state"] == "succeeded", job
    return proj, job_id, job


def test_receipt_and_default_policy(environment):
    client, srv, root = environment
    _, job_id, job = prepared(environment)
    response = client.get("/api/v1/storage/export-cache")
    assert response.status_code == 200, response.text
    listing = response.json()
    assert not listing["policy"]["automatic_enabled"]
    assert listing["policy"]["max_bytes"] == 4 * 1024**3
    artifact = listing["items"][0]
    assert artifact["id"] == job_id
    receipt = json.loads((root / "managed" / artifact["receipt_path"]).read_bytes())
    assert receipt["result"]["sha256"] == job["result"]["sha256"]
    assert receipt["manifest"]["approved_release"] is False


def test_cleanup_preserves_history_and_retry(environment):
    client, srv, root = environment
    _, job_id, job = prepared(environment)
    preview = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [job_id]})
    assert preview.status_code == 200, preview.text
    body = {"token": preview.json()["token"]}
    headers = {"Idempotency-Key": uid()}
    first = client.post("/api/v1/storage/export-cache/apply", json=body, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["deleted_bytes"] == job["result"]["bytes"], first.json()
    assert not (root / f"export-cache/{job_id}.zip").exists()
    second = client.post("/api/v1/storage/export-cache/apply", json=body, headers=headers)
    assert second.json() == first.json()
    assert client.get(f"/api/v1/jobs/{job_id}").json()["result"] == job["result"]
    assert client.get(f"/api/v1/working-exports/{job_id}/download").status_code == 410


def test_pin_and_download_protect_preview(environment):
    client, srv, _ = environment
    _, ident, _ = prepared(environment)
    response = client.patch(f"/api/v1/storage/export-cache/{ident}", json={"pinned": True})
    assert response.status_code == 200
    preview = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()
    assert preview["reclaimable_bytes"] == 0
    client.patch(f"/api/v1/storage/export-cache/{ident}", json={"pinned": False})
    with srv.export_cache.download(
        client.app.state.service.login("admin", "a-strong-test-password")["user"], ident
    ):
        preview = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()
        assert preview["reclaimable_bytes"] == 0


def test_same_frozen_export_one_physical_zip(environment):
    client, _, root = environment
    proj, first, _ = prepared(environment)
    second = start(client, proj).json()["job_id"]
    job = wait(client, second)
    assert job["state"] == "succeeded", job
    assert job["result"]["reused"] is True
    assert len(list((root / "export-cache").glob("*.zip"))) == 1
    assert client.get(f"/api/v1/working-exports/{second}/download").status_code == 200
    assert first != second


def test_storage_admin_only(environment):
    from test_team import create_user

    client, srv, _ = environment
    create_user(client, "viewer-storage")
    token = srv.login("viewer-storage", "a-long-user-password")["token"]
    response = client.get("/api/v1/storage/usage", headers={"Authorization": "Bearer " + token})
    assert response.status_code == 403


def test_reports_reject_external_destination(environment):
    client, _, root = environment
    response = client.post("/api/v1/storage/reports", json={"destination": str(root.parent / "outside.json")})
    assert response.status_code == 422
    assert not (root.parent / "outside.json").exists()
    response = client.post("/api/v1/storage/reports?deep=false", json={})
    assert response.status_code == 200, response.text
    assert client.get("/api/v1/storage/reports/" + response.json()["id"]).status_code == 200


def test_reprepare_reuses_identical_snapshot_across_job_lineage(environment):
    client, _, root = environment
    proj, first, _ = prepared(environment)
    second = start(client, proj).json()["job_id"]
    assert wait(client, second)["state"] == "succeeded"
    for source in (first, second):
        response = client.post(
            f"/api/v1/working-exports/{source}/reprepare", json={}, headers={"Idempotency-Key": uid()}
        )
        assert response.status_code == 202, response.text
        assert wait(client, response.json()["job_id"])["result"]["reused"]
    assert len(list((root / "export-cache").glob("*.zip"))) == 1


def test_transient_unlink_failure_allows_new_preview(environment, monkeypatch):
    client, srv, _ = environment
    _, ident, _ = prepared(environment)
    preview = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()
    with monkeypatch.context() as patch:
        patch.setattr(
            srv.export_cache.boundary,
            "unlink_registered",
            lambda *a: (_ for _ in ()).throw(PermissionError("sharing violation")),
        )
        result = client.post(
            "/api/v1/storage/export-cache/apply",
            json={"token": preview["token"]},
            headers={"Idempotency-Key": uid()},
        )
        assert result.json()["entries"][0]["status"] == "failed"
    assert client.get(f"/api/v1/working-exports/{ident}/download").status_code == 200
    fresh = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()
    assert fresh["reclaimable_bytes"] > 0


def test_export_reads_use_pinned_boundary(environment, monkeypatch):
    client, srv, root = environment
    proj, _ = labeled(client, root, count=3)

    def unpinned(*args):
        raise AssertionError("Export attempted an unpinned managed read")

    # Snapshot preparation remains the existing authorized service workflow.
    from visionlabel import working_export

    original = working_export._run_export

    def guarded(*args, **kwargs):
        with monkeypatch.context() as patch:
            patch.setattr(srv.blobs, "read", unpinned)
            patch.setattr(srv.blobs, "json", unpinned)
            return original(*args, **kwargs)

    monkeypatch.setattr(working_export, "_run_export", guarded)
    job = wait(client, start(client, proj).json()["job_id"])
    assert job["state"] == "succeeded", job


def test_policy_requires_review_and_stale_preview_rejected(environment):
    client, _, _ = environment
    body = {"expected_generation": 1, "max_bytes": 1024**3, "max_age_days": 7, "automatic_enabled": True}
    assert client.patch("/api/v1/storage/policy", json=body).status_code == 409
    preview = client.post("/api/v1/storage/policy/preview", json=body)
    assert preview.status_code == 200, preview.text
    response = client.patch("/api/v1/storage/policy", json=body | {"preview_token": preview.json()["token"]})
    assert response.status_code == 200, response.text
    assert response.json()["generation"] == 2
    assert (
        client.patch(
            "/api/v1/storage/policy", json=body | {"preview_token": preview.json()["token"]}
        ).status_code
        == 409
    )


def test_pin_after_preview_and_reprepare_evicted_snapshot(environment):
    client, _, _ = environment
    _, ident, original = prepared(environment)
    preview = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()
    client.patch(f"/api/v1/storage/export-cache/{ident}", json={"pinned": True})
    result = client.post(
        "/api/v1/storage/export-cache/apply",
        json={"token": preview["token"]},
        headers={"Idempotency-Key": uid()},
    ).json()
    assert result["deleted_bytes"] == 0
    client.patch(f"/api/v1/storage/export-cache/{ident}", json={"pinned": False})
    preview = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()
    client.post(
        "/api/v1/storage/export-cache/apply",
        json={"token": preview["token"]},
        headers={"Idempotency-Key": uid()},
    )
    response = client.post(f"/api/v1/working-exports/{ident}/reprepare", headers={"Idempotency-Key": uid()})
    assert response.status_code == 202, response.text
    new_job = wait(client, response.json()["job_id"])
    assert new_job["state"] == "succeeded", new_job
    assert client.get(f"/api/v1/jobs/{ident}").json()["result"] == original["result"]


def test_nonregistered_zip_counts_towards_budget(environment):
    client, srv, root = environment
    import pytest

    from visionlabel.domain import Problem

    (root / "export-cache").mkdir(exist_ok=True)
    with (root / "export-cache/unknown.zip").open("wb") as stream:
        stream.truncate(2 * 1024**2)
    with srv.db.transaction() as conn:
        conn.exec_driver_sql("UPDATE storage_policy SET max_bytes=1048576")
    with pytest.raises(Problem, match="cache space"):
        with srv.export_cache.admission(100):
            pytest.fail("Unregistered archive did not count towards budget")


def test_legacy_adoption_is_nondestructive(environment, monkeypatch):
    client, srv, root = environment
    with monkeypatch.context() as patch:
        patch.setattr(srv.export_cache, "register", lambda *args, **kwargs: None)
        _, ident, original = prepared(environment)
    path = root / f"export-cache/{ident}.zip"
    before = path.read_bytes()
    response = client.post("/api/v1/storage/export-cache/adopt", json={})
    assert response.status_code == 200, response.text
    assert response.json()["items"] == [{"id": ident, "status": "protected"}]
    assert path.read_bytes() == before
    listing = client.get("/api/v1/storage/export-cache").json()
    assert listing["items"][0]["legacy_protected"]
    assert client.post("/api/v1/storage/export-cache/adopt", json={}).json()["items"] == []
    srv.export_cache.maintain()
    assert path.read_bytes() == before
    assert client.get(f"/api/v1/jobs/{ident}").json()["result"] == original["result"]


def test_receipt_backup_restore_and_eviction_recovery(environment, tmp_path):
    import pytest

    from visionlabel.export_cache import ExportCache
    from visionlabel.operations import backup, restore, verify_backup
    from visionlabel.service import Service

    client, srv, root = environment
    _, ident, _ = prepared(environment)
    token = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()[
        "token"
    ]
    actor = srv.login("admin", "a-strong-test-password")["user"]

    def fail(point):
        if point == "storage_after_unlink":
            raise RuntimeError("simulated process interruption")

    srv.fault = fail
    with pytest.raises(RuntimeError):
        srv.export_cache.apply(actor, token, uid())
    srv.fault = lambda _: None
    srv.export_cache = ExportCache(srv)
    assert srv.export_cache.artifacts()[0]["state"] == "EVICTED"
    srv.close()
    backup(root, tmp_path / "backup")
    verify_backup(tmp_path / "backup")
    restore(tmp_path / "backup", tmp_path / "restored")
    restored = Service(tmp_path / "restored")
    try:
        a = restored.export_cache.artifacts()[0]
        assert a["id"] == ident
        assert (restored.root / "managed" / a["receipt_path"]).is_file()
    finally:
        restored.close()


def test_checkpoint_restore_after_cache_cleanup(environment):
    from test_checkpoints import apply_preview, checkpoint, preview

    from visionlabel.domain import digest

    client, srv, root = environment
    proj, _ = labeled(client, root, count=3)
    version = checkpoint(client, proj, "before-cleanup")
    snapshot = srv.blobs.read(version["blob_path"], version["sha256"])
    job = wait(client, start(client, proj, checkpoint_id=version["id"]).json()["job_id"])
    assert job["state"] == "succeeded"
    ids = [a["id"] for a in srv.export_cache.artifacts()]
    proposal = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": ids}).json()
    result = client.post(
        "/api/v1/storage/export-cache/apply",
        json={"token": proposal["token"]},
        headers={"Idempotency-Key": uid()},
    )
    assert result.json()["deleted_bytes"] > 0, result.text
    restored = apply_preview(
        client, proj, preview(client, proj, "restored", "restore", checkpoint_id=version["id"])
    )
    assert restored["state"] == "succeeded", restored
    assert digest(srv.blobs.read(version["blob_path"], version["sha256"])) == digest(snapshot)
    again = wait(client, start(client, proj, checkpoint_id=version["id"]).json()["job_id"])
    assert again["state"] == "succeeded", again


def test_disconnect_releases_download_lease(environment):
    import asyncio

    from visionlabel.storage_api import ProtectedDownload

    _, srv, _ = environment
    _, ident, _ = prepared(environment)
    actor = srv.login("admin", "a-strong-test-password")["user"]
    response = ProtectedDownload(srv.export_cache, actor, ident)

    async def receive():
        return {"type": "http.disconnect"}

    async def send(_):
        raise OSError("client disconnected")

    async def execute():
        try:
            await response({"type": "http", "asgi": {"spec_version": "2.4"}}, receive, send)
        except Exception:
            pass

    asyncio.run(execute())
    assert srv.export_cache.active[ident] == 0


def test_stale_file_and_external_report_destinations_rejected(environment):
    client, _, root = environment
    _, ident, _ = prepared(environment)
    token = client.post("/api/v1/storage/export-cache/preview", json={"artifact_ids": [ident]}).json()[
        "token"
    ]
    (root / f"export-cache/{ident}.zip").write_bytes(b"changed")
    result = client.post(
        "/api/v1/storage/export-cache/apply", json={"token": token}, headers={"Idempotency-Key": uid()}
    )
    assert result.json()["deleted_bytes"] == 0
    assert (root / f"export-cache/{ident}.zip").read_bytes() == b"changed"

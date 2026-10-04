import errno
import json
import sqlite3
import subprocess
import sys

import pytest
from conftest import claim, import_files, project, save_body

from visionlabel.domain import Problem, uid
from visionlabel.operations import backup, restore, verify_backup
from visionlabel.service import Service


def test_single_service_and_backup_restore(environment, tmp_path):
    client, service, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    lease = claim(client, image["id"])
    saved = client.put(
        f"/api/v1/images/{image['id']}/annotation",
        json=save_body(proj),
        headers=dict(lease, **{"Idempotency-Key": uid()}),
    ).json()
    with pytest.raises(Problem, match="already open"):
        Service(root)
    with pytest.raises(Problem, match="already open"):
        backup(root, tmp_path / "backup")
    service.close()
    manifest = backup(root, tmp_path / "backup")
    assert len(manifest["files"]) == 3
    destination = tmp_path / "restored"
    restore(tmp_path / "backup", destination)
    restored = Service(destination)
    try:
        session = restored.login("admin", "a-strong-test-password")
        user = restored.authenticate(session["token"])
        loaded = restored.annotation(user, image["id"])
        assert loaded["annotation_sha256"] == saved["annotation_sha256"]
        with pytest.raises(Problem):
            restored.authenticate(client.headers["Authorization"][7:])
    finally:
        restored.close()


@pytest.fixture
def backup_fixture(environment, tmp_path):
    client, service, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    lease = claim(client, image["id"])
    response = client.put(
        f"/api/v1/images/{image['id']}/annotation",
        json=save_body(proj),
        headers=dict(lease, **{"Idempotency-Key": uid()}),
    )
    assert response.status_code == 200
    service.close()
    folder = tmp_path / "backup"
    manifest = backup(root, folder)
    return folder, manifest


def test_verify_backup_does_not_modify_snapshot_and_cli(backup_fixture):
    folder, manifest = backup_fixture
    before = {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}
    assert verify_backup(folder) == manifest
    result = subprocess.run(
        [sys.executable, "-m", "visionlabel.cli", "verify-backup", "--backup-set", str(folder)],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    assert before == {p.relative_to(folder): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


@pytest.mark.parametrize(
    "corruption", ["database", "blob", "missing", "manifest", "duplicate", "version", "sidecar"]
)
def test_restore_corruption_never_publishes(backup_fixture, tmp_path, corruption):
    folder, manifest = backup_fixture
    blob = folder / "managed" / manifest["files"][0]["path"]
    if corruption == "database":
        (folder / "database.sqlite3").write_bytes(b"broken")
    elif corruption == "blob":
        blob.write_bytes(b"broken")
    elif corruption == "missing":
        blob.unlink()
    elif corruption == "manifest":
        (folder / "backup_manifest.json").write_text("{broken", encoding="utf-8")
    elif corruption == "duplicate":
        manifest["files"].append(manifest["files"][0])
        (folder / "backup_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    elif corruption == "version":
        manifest["schema_version"] = 999
        (folder / "backup_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    else:
        (folder / "database.sqlite3-wal").write_bytes(b"unexpected sidecar")
    destination = tmp_path / "restore"
    with pytest.raises(Problem):
        restore(folder, destination)
    assert not destination.exists()


def test_restore_copy_failure_and_source_change_never_publish(backup_fixture, tmp_path, monkeypatch):
    import visionlabel.operations as operations

    folder, _ = backup_fixture
    original = operations._copy_synced

    def disk_full(source, target):
        original(source, target)
        raise OSError(errno.ENOSPC, "Injected disk full")

    monkeypatch.setattr(operations, "_copy_synced", disk_full)
    with pytest.raises(OSError):
        restore(folder, tmp_path / "full")
    assert not (tmp_path / "full").exists()

    def corrupt_copy(source, target):
        original(source, target)
        target.write_bytes(b"changed after validation")

    monkeypatch.setattr(operations, "_copy_synced", corrupt_copy)
    with pytest.raises(Problem, match="copied blob"):
        restore(folder, tmp_path / "changed")
    assert not (tmp_path / "changed").exists()
    assert not list(tmp_path.glob(".visionlabel-restore-*"))


def test_restore_unicode_paths_and_invalidates_sessions(backup_fixture, tmp_path):
    folder, manifest = backup_fixture
    target = tmp_path / "การกู้คืน with spaces"
    restore(folder, target)
    for item in manifest["files"]:
        assert (target / "managed" / item["path"]).read_bytes() == (
            folder / "managed" / item["path"]
        ).read_bytes()
    connection = sqlite3.connect(target / "db/data_tracking.sqlite3")
    try:
        assert (
            connection.execute("SELECT COUNT(*) FROM auth_tokens WHERE revoked_at IS NULL").fetchone()[0] == 0
        )
        assert (
            connection.execute(
                "SELECT COUNT(*) FROM task_claims WHERE expires_at != '1970-01-01T00:00:00Z'"
            ).fetchone()[0]
            == 0
        )
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()
    with pytest.raises(Problem):
        restore(folder, target)


def test_failed_backup_does_not_publish(environment, tmp_path, monkeypatch):
    import visionlabel.operations as operations

    client, service, root = environment
    project(client)
    service.close()

    def fail_sync(fd):
        raise OSError(errno.ENOSPC, "Injected disk full")

    monkeypatch.setattr(operations.os, "fsync", fail_sync)
    with pytest.raises(OSError):
        backup(root, tmp_path / "failed")
    assert not (tmp_path / "failed").exists()
    assert not list(tmp_path.glob(".visionlabel-backup-*"))

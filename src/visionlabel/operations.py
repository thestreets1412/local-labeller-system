"""Offline Phase 1 backup/restore. Never copy a live SQLite main file alone."""

import json
import msvcrt
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

from .domain import Problem, canonical, digest
from .storage import contained, local_directory


class DirectoryLock:
    def __init__(self, root: Path):
        self.path = root / "service.lock"
        self.stream = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.stream.write(b"0")
            self.stream.flush()
        self.stream.seek(0)
        try:
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            self.stream.close()
            raise Problem(
                "SERVICE_RUNNING",
                "This data directory is already open. Stop its server before backup or maintenance.",
                409,
            ) from exc
        self.closed = False

    def close(self):
        if not self.closed:
            self.stream.seek(0)
            msvcrt.locking(self.stream.fileno(), msvcrt.LK_UNLCK, 1)
            self.stream.close()
            self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def references(connection):
    return sorted(
        {
            (path, sha)
            for table in ("assets", "class_schemas", "annotation_revisions")
            for path, sha in connection.execute(f"SELECT blob_path,sha256 FROM {table}")
        }
    )


def check_database(connection):
    if (
        connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok"
        or connection.execute("PRAGMA foreign_key_check").fetchall()
    ):
        raise Problem("CORRUPT_DATABASE", "Database integrity check failed.", 503)


def backup(root: Path, destination: Path):
    root = local_directory(root)
    destination = local_directory(destination)
    if destination.exists() or destination.is_relative_to(root):
        raise Problem("INVALID_BACKUP", "Choose a new backup directory outside the server data directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".visionlabel-backup-", dir=destination.parent) as stage:
        candidate = Path(stage) / "backup"
        result = _backup_snapshot(root, candidate)
        verify_backup(candidate)
        # Same-volume rename on Windows fails if destination appeared meanwhile.
        os.rename(candidate, destination)
    return result


def _backup_snapshot(root: Path, destination: Path):
    root = local_directory(root)
    destination = destination.resolve()
    if destination.exists() or destination.is_relative_to(root):
        raise Problem("INVALID_BACKUP", "Choose a new backup directory outside the server data directory.")
    with DirectoryLock(root):
        dbpath = root / "db" / "data_tracking.sqlite3"
        if not dbpath.is_file():
            raise Problem("NOT_FOUND", "Initialize the server before backing up.", 404)
        destination.mkdir(parents=True)
        snapshot = destination / "database.sqlite3"
        source = sqlite3.connect(dbpath)
        target = sqlite3.connect(snapshot)
        try:
            source.backup(target)
            check_database(target)
            files = []
            for relative, sha in references(target):
                content = contained(root / "managed", relative, True).read_bytes()
                if digest(content) != sha:
                    raise Problem(
                        "CORRUPT_BLOB", "Backup stopped: a referenced blob failed verification.", 503
                    )
                path = contained(destination / "managed", relative)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("xb") as stream:
                    stream.write(content)
                    stream.flush()
                    os.fsync(stream.fileno())
                if digest(path.read_bytes()) != sha:
                    raise Problem("CORRUPT_BACKUP", "Backup verification failed.", 503)
                files.append({"path": relative, "sha256": sha, "bytes": len(content)})
        finally:
            target.close()
            source.close()
        manifest = {
            "schema_version": 1,
            "state": "COMPLETE",
            "database_sha256": digest(snapshot.read_bytes()),
            "files": files,
            "app_version": "0.1.0",
            "secrets_included": False,
        }
        with (destination / "backup_manifest.json").open("xb") as stream:
            stream.write(canonical(manifest))
            stream.flush()
            os.fsync(stream.fileno())
        return manifest


def verify_backup(source: Path):
    """Read-only integrity verification; checksum validity does not establish trust."""
    source = source.resolve()
    try:
        manifest_path = contained(source, "backup_manifest.json", True)
        if manifest_path.stat().st_size > 64 * 1024 * 1024:
            raise ValueError("Backup manifest exceeds 64 MiB.")
        manifest = json.loads(manifest_path.read_bytes())
        if (
            not isinstance(manifest, dict)
            or manifest.get("schema_version") != 1
            or manifest.get("state") != "COMPLETE"
        ):
            raise ValueError("Unsupported or incomplete backup manifest.")
        if not isinstance(manifest.get("files"), list):
            raise ValueError("Backup file list is missing.")
        paths = set()
        for item in manifest["files"]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes"}:
                raise ValueError("Invalid backup file entry.")
            if not isinstance(item["path"], str) or item["path"] in paths:
                raise ValueError("Duplicate or invalid backup path.")
            paths.add(item["path"])
            if type(item["bytes"]) is not int or item["bytes"] < 0:
                raise ValueError("Invalid backup byte count.")
        snapshot = contained(source, "database.sqlite3", True)
        if digest(snapshot.read_bytes()) != manifest["database_sha256"]:
            raise ValueError("Backup database checksum failed.")
    except (OSError, KeyError, TypeError, ValueError) as exc:
        raise Problem("CORRUPT_BACKUP", "Invalid backup manifest or database: " + str(exc), 503) from exc
    if any(snapshot.with_name(snapshot.name + suffix).exists() for suffix in ("-wal", "-shm", "-journal")):
        raise Problem("CORRUPT_BACKUP", "Backup snapshots must not have SQLite sidecar files.", 503)
    connection = sqlite3.connect(f"{snapshot.as_uri()}?mode=ro&immutable=1", uri=True)
    try:
        check_database(connection)
        required = references(connection)
        provided = sorted((f["path"], f["sha256"]) for f in manifest["files"])
        if required != provided:
            raise Problem("CORRUPT_BACKUP", "Backup manifest does not match database references.", 503)
    except sqlite3.DatabaseError as exc:
        raise Problem("CORRUPT_BACKUP", "Backup database is unreadable or unsupported.", 503) from exc
    finally:
        connection.close()
    for item in manifest["files"]:
        data = contained(source / "managed", item["path"], True).read_bytes()
        if digest(data) != item["sha256"] or len(data) != item["bytes"]:
            raise Problem("CORRUPT_BACKUP", "Backup blob checksum failed.", 503)
    return manifest


def restore(source: Path, destination: Path):
    source = source.resolve()
    destination = local_directory(destination)
    if destination.exists() or destination.is_relative_to(source):
        raise Problem(
            "INVALID_RESTORE",
            "Restore requires a new destination outside the backup. Never overwrite a live server.",
        )
    manifest = verify_backup(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".visionlabel-restore-", dir=destination.parent) as stage:
        candidate = Path(stage) / "data"
        _restore_snapshot(source, candidate, manifest)
        os.rename(candidate, destination)
    return manifest


def _restore_snapshot(source, destination, manifest):
    (destination / "db").mkdir(parents=True)
    for item in manifest["files"]:
        target = contained(destination / "managed", item["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        _copy_synced(contained(source / "managed", item["path"], True), target)
        data = target.read_bytes()
        if digest(data) != item["sha256"] or len(data) != item["bytes"]:
            raise Problem(
                "CORRUPT_BACKUP", "Source changed during restore; copied blob verification failed.", 503
            )
    dbpath = destination / "db" / "data_tracking.sqlite3"
    _copy_synced(contained(source, "database.sqlite3", True), dbpath)
    if digest(dbpath.read_bytes()) != manifest["database_sha256"]:
        raise Problem("CORRUPT_BACKUP", "Backup database checksum failed.", 503)
    restored = sqlite3.connect(dbpath)
    try:
        restored.execute("UPDATE task_claims SET generation=generation+1,expires_at='1970-01-01T00:00:00Z'")
        restored.execute("UPDATE auth_tokens SET revoked_at='1970-01-01T00:00:00Z'")
        restored.execute("UPDATE jobs SET state='failed' WHERE state IN ('queued','running')")
        restored.commit()
        check_database(restored)
    finally:
        restored.close()


def _copy_synced(source, target):
    with source.open("rb") as incoming, target.open("xb") as outgoing:
        shutil.copyfileobj(incoming, outgoing)
        outgoing.flush()
        os.fsync(outgoing.fileno())

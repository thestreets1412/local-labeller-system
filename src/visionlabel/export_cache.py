"""Root-only export lifecycle. Job evidence survives physical ZIP eviction."""

import json
import shutil
import threading
import zipfile
from contextlib import contextmanager
from functools import wraps
from typing import Any

from .database import row, rows
from .domain import Problem, canonical, digest, uid
from .storage_boundary import StorageBoundary
from .storage_policy import select_evictions


def timestamp():
    from .service import now

    return now()


def artifact_key(snapshot, recipe):
    return digest(canonical({"snapshot": snapshot, "recipe": recipe}))


def recipe():
    from .working_export import FORMAT_VERSION, PREPARE_SCRIPT, PROFILE, SPLIT_ALGORITHM

    return {
        "format_version": FORMAT_VERSION,
        "split_algorithm": SPLIT_ALGORITHM,
        "archive_profile": PROFILE,
        "templates_sha256": digest((PREPARE_SCRIPT + "training-template-1").encode()),
    }


def root_guarded(function):
    @wraps(function)
    def guarded(self, *args, **kwargs):
        with self.boundary.database():
            return function(self, *args, **kwargs)

    return guarded


class ExportCache:
    def __init__(self, srv):
        self.srv = srv
        self.boundary = StorageBoundary(srv.root)
        self.lock = threading.RLock()
        self.active = {}
        self.reserved = 0
        self.building = set()
        self.last_error = None
        # Never delete on upgrade/startup. Reconcile only interrupted journal state.
        with srv.db.transaction() as conn:
            for a in rows(conn, "SELECT * FROM export_artifacts WHERE state='EVICTING'"):
                try:
                    self.boundary.inventory_entry(a["path"])
                    state = "ACTIVE"
                except FileNotFoundError:
                    state = "EVICTED"
                except (OSError, Problem):
                    continue
                conn.exec_driver_sql("UPDATE export_artifacts SET state=? WHERE id=?", (state, a["id"]))

    @root_guarded
    def admin(self, actor):
        with self.srv.db.engine.connect() as conn:
            self.srv.administrator(conn, actor)

    @root_guarded
    def policy(self):
        with self.srv.db.engine.connect() as conn:
            return row(conn, "SELECT * FROM storage_policy WHERE id=1")

    @root_guarded
    def artifacts(self):
        with self.srv.db.engine.connect() as conn:
            records = rows(
                conn,
                "SELECT a.*,r.blob_path AS receipt_path FROM export_artifacts a JOIN export_receipts r ON r.id=a.receipt_id ORDER BY a.last_access_at DESC,a.id",
            )
        return [a | {"in_flight": bool(self.active.get(a["id"]))} for a in records]

    def accounted_artifacts(self):
        records = self.artifacts()
        known = {a["path"] for a in records if a["state"] != "EVICTED"}
        try:
            entries = list(self.boundary.walk("export-cache"))
        except FileNotFoundError:
            entries = []
        for entry in entries:
            if entry["blocked"]:
                raise Problem(
                    "STORAGE_BOUNDARY",
                    "Export cache contains a blocked path. Inspect it before building or enabling retention.",
                    409,
                )
            path = entry["path"]
            if entry["directory"] or path in known or path in self.building:
                continue
            records.append(
                {
                    "id": "unknown:" + path,
                    "path": path,
                    "bytes": entry["bytes"],
                    "state": "ACTIVE",
                    "pinned": False,
                    "legacy_protected": True,
                    "in_flight": False,
                    "last_access_at": timestamp(),
                }
            )
        return records

    @root_guarded
    def register(self, conn, job_id, snapshot, result, manifest, legacy=False):
        record = {
            "version": 1,
            "job_id": job_id,
            "snapshot": snapshot,
            "result": result,
            "manifest": manifest,
            "recipe": None if legacy else recipe(),
            "created_at": timestamp(),
        }
        raw = canonical(record)
        sha = digest(raw)
        relative = f"export-receipts/{sha}.json"
        self.boundary.mkdir("managed/export-receipts")
        try:
            with self.boundary.open_new("managed/" + relative) as stream:
                stream.write(raw)
        except FileExistsError:
            if self.boundary.hash("managed/" + relative) != sha:
                raise Problem(
                    "CORRUPT_RECEIPT", "Receipt checksum mismatch. Inspect storage before cleanup.", 503
                ) from None
        conn.exec_driver_sql(
            "INSERT INTO export_receipts VALUES (?,?,?,?)", (job_id, relative, sha, timestamp())
        )
        key = "legacy:" + job_id if legacy else artifact_key(snapshot, recipe())
        conn.exec_driver_sql(
            "INSERT INTO export_artifacts VALUES (?,?,?,?,?,?,?,'ACTIVE',0,?,?)",
            (
                job_id,
                snapshot["project_id"],
                key,
                f"export-cache/{job_id}.zip",
                result["sha256"],
                result["bytes"],
                job_id,
                int(legacy),
                timestamp(),
            ),
        )
        conn.exec_driver_sql("INSERT INTO export_job_artifacts VALUES (?,?)", (job_id, job_id))

    @root_guarded
    def adopt(self, actor):
        self.admin(actor)
        results = []
        with self.lock:
            with self.srv.db.engine.connect() as conn:
                jobs = rows(
                    conn,
                    "SELECT j.* FROM jobs j LEFT JOIN export_job_artifacts l ON l.job_id=j.id WHERE j.type='working-export' AND j.state='succeeded' AND l.job_id IS NULL",
                )
            for job in jobs:
                try:
                    result, snapshot = json.loads(job["result_json"]), json.loads(job["payload_json"])
                    path = f"export-cache/{job['id']}.zip"
                    with self.boundary.open_read(path) as stream:
                        import hashlib

                        if hashlib.file_digest(stream, "sha256").hexdigest() != result["sha256"]:
                            raise ValueError("Archive checksum mismatch")
                        stream.seek(0)
                        with zipfile.ZipFile(stream) as archive:
                            if archive.getinfo("manifest.json").file_size > 128 * 1024**2:
                                raise ValueError("Manifest too large")
                            manifest = json.loads(archive.read("manifest.json"))
                    if (
                        manifest["snapshot_sha256"] != digest(canonical(snapshot))
                        or manifest["project_id"] != job["project_id"]
                    ):
                        raise ValueError("Snapshot evidence mismatch")
                    with self.srv.db.transaction() as conn:
                        self.register(conn, job["id"], snapshot, result, manifest, True)
                        self.srv.audit(conn, actor, "storage.archive_adopted", job["id"], None, {}, uid())
                    results.append({"id": job["id"], "status": "protected"})
                except (OSError, ValueError, KeyError, zipfile.BadZipFile, Problem) as exc:
                    results.append({"id": job["id"], "status": "blocked", "reason": str(exc)})
        return {"items": results}

    def verified(self, a):
        identity = self.boundary.inventory_entry(a["path"])
        if identity["blocked"] or identity["links"] != 1 or identity["bytes"] != a["bytes"]:
            raise Problem(
                "CORRUPT_EXPORT",
                "Archive identity is unsafe. Inspect storage and prepare another export.",
                409,
            )
        if self.boundary.hash(a["path"]) != a["sha256"]:
            raise Problem(
                "CORRUPT_EXPORT",
                "Archive checksum mismatch. Inspect storage and prepare another export.",
                503,
            )
        with self.srv.db.engine.connect() as conn:
            receipt = row(conn, "SELECT * FROM export_receipts WHERE id=?", (a["receipt_id"],))
        if self.boundary.hash("managed/" + receipt["blob_path"]) != receipt["sha256"]:
            raise Problem(
                "CORRUPT_RECEIPT",
                "Export evidence is damaged. Restore verified evidence before cleanup.",
                503,
            )
        return identity

    @root_guarded
    def preview(self, actor, ids):
        from .service import after

        self.admin(actor)
        if len(ids) != len(set(ids)):
            raise Problem("VALIDATION_FAILED", "Select each archive only once.")
        entries, blocked = [], []
        with self.lock:
            available = {a["id"]: a for a in self.artifacts()}
            for ident in ids:
                a = available.get(ident)
                if not a or a["state"] != "ACTIVE" or a["pinned"] or a["in_flight"]:
                    blocked.append(
                        {
                            "id": ident,
                            "reason": "Archive is unavailable, pinned or in use. Refresh or unpin it first.",
                        }
                    )
                    continue
                try:
                    entries.append({"id": ident, "identity": self.verified(a), "sha256": a["sha256"]})
                except (OSError, Problem) as exc:
                    blocked.append({"id": ident, "reason": str(exc)})
            token, expires = uid(), after(600)
            policy = self.policy()
            with self.srv.db.transaction() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO storage_cleanup_operations VALUES (?,?,?,?,?,?,NULL)",
                    (
                        token,
                        actor["id"],
                        self.boundary.identity,
                        policy["generation"],
                        expires,
                        canonical(entries).decode(),
                    ),
                )
        return {
            "token": token,
            "root": str(self.boundary.root),
            "root_identity": self.boundary.identity,
            "expires_at": expires,
            "entries": entries,
            "blocked": blocked,
            "reclaimable_bytes": sum(e["identity"]["bytes"] for e in entries),
        }

    def _evict(self, a, identity):
        with self.srv.db.transaction() as conn:
            conn.exec_driver_sql("UPDATE export_artifacts SET state='EVICTING' WHERE id=?", (a["id"],))
        self.srv.fault("storage_before_unlink")
        try:
            self.boundary.unlink_registered(a["path"], identity)
        except FileNotFoundError:
            pass
        except (OSError, Problem):
            # A recoverable sharing violation is not a process crash. Keep the
            # still-present archive downloadable and eligible for a fresh preview.
            with self.srv.db.transaction() as conn:
                conn.exec_driver_sql("UPDATE export_artifacts SET state='ACTIVE' WHERE id=?", (a["id"],))
            raise
        self.srv.fault("storage_after_unlink")
        with self.srv.db.transaction() as conn:
            conn.exec_driver_sql("UPDATE export_artifacts SET state='EVICTED' WHERE id=?", (a["id"],))

    @root_guarded
    def apply(self, actor, token, key):
        self.admin(actor)
        with self.lock:
            with self.boundary.directory():
                with self.srv.db.transaction() as conn:
                    replay = self.srv.replay(conn, actor, "storage-cleanup", key, {"token": token})
                    if replay:
                        return replay
                    op = row(
                        conn,
                        "SELECT * FROM storage_cleanup_operations WHERE id=? AND actor_id=?",
                        (token, actor["id"]),
                    )
                    if not op:
                        raise Problem("NOT_FOUND", "Cleanup preview not found. Preview again.", 404)
                    if op["result_json"]:
                        return json.loads(op["result_json"])
                    if not isinstance(json.loads(op["entries_json"]), list):
                        raise Problem(
                            "INVALID_PREVIEW",
                            "This is not a cleanup preview. Preview archive cleanup first.",
                            409,
                        )
                    if (
                        op["root_identity"] != self.boundary.identity
                        or op["expires_at"] < timestamp()
                        or op["generation"] != self.policy()["generation"]
                    ):
                        raise Problem(
                            "STALE_PREVIEW",
                            "Root or policy changed, or preview expired. Preview cleanup again.",
                            409,
                        )
                result: dict[str, Any] = {"deleted_bytes": 0, "entries": [], "audit_id": uid()}
                available = {a["id"]: a for a in self.artifacts()}
                for entry in json.loads(op["entries_json"]):
                    a = available[entry["id"]]
                    outcome = {"id": a["id"], "status": "skipped"}
                    try:
                        if a["pinned"] or a["in_flight"]:
                            outcome["reason"] = "Archive is pinned or in use. Refresh and preview again."
                        elif a["state"] == "EVICTED":
                            outcome["status"] = "already_removed"
                        else:
                            identity = self.verified(a)
                            if identity != entry["identity"]:
                                raise Problem("STALE_PREVIEW", "File changed. Preview cleanup again.", 409)
                            self._evict(a, identity)
                            result["deleted_bytes"] += a["bytes"]
                            outcome["status"] = "deleted"
                    except (OSError, Problem) as exc:
                        outcome.update(status="failed", reason=str(exc))
                    result["entries"].append(outcome)
                with self.srv.db.transaction() as conn:
                    self.srv.audit(conn, actor, "storage.cleanup", token, None, result, result["audit_id"])
                    conn.exec_driver_sql(
                        "UPDATE storage_cleanup_operations SET result_json=? WHERE id=?",
                        (canonical(result).decode(), token),
                    )
                    self.srv.remember(conn, actor, "storage-cleanup", key, {"token": token}, result)
                return result

    @root_guarded
    def pin(self, actor, ident, pinned):
        self.admin(actor)
        with self.lock, self.srv.db.transaction() as conn:
            a = row(conn, "SELECT * FROM export_artifacts WHERE id=?", (ident,))
            if not a or a["state"] != "ACTIVE":
                raise Problem("NOT_FOUND", "Cached archive unavailable. Refresh the list.", 404)
            conn.exec_driver_sql("UPDATE export_artifacts SET pinned=? WHERE id=?", (int(pinned), ident))
            self.srv.audit(conn, actor, "storage.pin", ident, None, {"pinned": pinned}, uid())
        return {"id": ident, "pinned": pinned}

    @root_guarded
    def preview_policy(self, actor, body):
        from .service import after

        self.admin(actor)
        body = {k: v for k, v in body.items() if k != "preview_token"}
        with self.lock:
            policy = self.policy()
            if policy["generation"] != body["expected_generation"]:
                raise Problem("STALE_POLICY", "Storage policy changed. Refresh and preview again.", 409)
            selection = select_evictions(
                self.accounted_artifacts(),
                max_bytes=body["max_bytes"],
                max_age_days=body["max_age_days"],
                now=timestamp(),
            )
            token, expires = uid(), after(600)
            payload = {"kind": "policy", "body": body}
            with self.srv.db.transaction() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO storage_cleanup_operations VALUES (?,?,?,?,?,?,NULL)",
                    (
                        token,
                        actor["id"],
                        self.boundary.identity,
                        policy["generation"],
                        expires,
                        canonical(payload).decode(),
                    ),
                )
            return {
                "token": token,
                "root": str(self.boundary.root),
                "expires_at": expires,
                "proposal": body,
                "impact": selection,
                "note": "Automatic cleanup applies only when enabled. Legacy archives remain protected; select them explicitly for manual cleanup.",
            }

    @root_guarded
    def update_policy(self, actor, body):
        self.admin(actor)
        token = body.pop("preview_token", None)
        with self.lock, self.srv.db.transaction() as conn:
            with self.boundary.directory():
                pass
            old = row(conn, "SELECT * FROM storage_policy WHERE id=1")
            if body["expected_generation"] != old["generation"]:
                raise Problem("STALE_POLICY", "Storage policy changed. Refresh and try again.", 409)
            preview = row(
                conn,
                "SELECT * FROM storage_cleanup_operations WHERE id=? AND actor_id=?",
                (token, actor["id"]),
            )
            if (
                not preview
                or preview["root_identity"] != self.boundary.identity
                or preview["expires_at"] < timestamp()
                or json.loads(preview["entries_json"]) != {"kind": "policy", "body": body}
            ):
                raise Problem(
                    "POLICY_PREVIEW_REQUIRED",
                    "Preview the exact retention policy for this root before applying it.",
                    409,
                )
            conn.exec_driver_sql(
                "UPDATE storage_policy SET generation=generation+1,max_bytes=?,max_age_days=?,automatic_enabled=? WHERE id=1",
                (body["max_bytes"], body["max_age_days"], int(body["automatic_enabled"])),
            )
            self.srv.audit(conn, actor, "storage.policy", "1", None, body, uid())
        return self.policy()

    @root_guarded
    def maintain(self, reserve_bytes=0):
        with self.lock, self.boundary.directory():
            policy = self.policy()
            selection = select_evictions(
                self.accounted_artifacts(),
                max_bytes=policy["max_bytes"],
                max_age_days=policy["max_age_days"],
                now=timestamp(),
                reserve_bytes=reserve_bytes + self.reserved,
            )
            available = {a["id"]: a for a in self.artifacts()}
            for ident in selection["candidate_ids"] if policy["automatic_enabled"] else []:
                try:
                    a = available[ident]
                    self._evict(a, self.verified(a))
                    with self.srv.db.transaction() as conn:
                        self.srv.audit(
                            conn,
                            {"id": None},
                            "storage.automatic_eviction",
                            ident,
                            None,
                            {"bytes": a["bytes"]},
                            uid(),
                        )
                except (OSError, Problem) as exc:
                    self.last_error = str(exc)
            remaining = sum(a["bytes"] for a in self.accounted_artifacts() if a["state"] != "EVICTED")
            if reserve_bytes and remaining + self.reserved + reserve_bytes > policy["max_bytes"]:
                raise Problem(
                    "CACHE_FULL",
                    "Not enough cache space. Unpin an export, remove eligible archives, or increase the limit.",
                    409,
                )

    @contextmanager
    def admission(self, estimate, job_id=None):
        with self.lock:
            self.maintain(estimate)
            with self.boundary.directory() as root:
                if shutil.disk_usage(root).free < estimate + self.reserved + 1024**3:
                    raise Problem(
                        "DISK_FULL",
                        "Not enough free space inside the configured root. Free space before preparing an export.",
                        409,
                    )
            self.reserved += estimate
            if job_id:
                self.building.add(f"export-cache/{job_id}.partial")
        try:
            yield
        finally:
            with self.lock:
                self.reserved -= estimate
                if job_id:
                    self.building.discard(f"export-cache/{job_id}.partial")

    @root_guarded
    def reuse(self, actor, job_id, snapshot):
        with self.lock:
            with self.srv.db.engine.connect() as conn:
                self.srv.maintain(conn, actor, snapshot["project_id"])
                a = row(
                    conn,
                    "SELECT * FROM export_artifacts WHERE cache_key=? AND state='ACTIVE' ORDER BY last_access_at DESC LIMIT 1",
                    (artifact_key(snapshot, recipe()),),
                )
            if not a:
                return False
            self.verified(a)
            with self.srv.db.transaction() as conn:
                self.srv.maintain(conn, actor, snapshot["project_id"])
                original = row(conn, "SELECT result_json FROM jobs WHERE id=?", (a["id"],))
                result = json.loads(original["result_json"]) | {"reused": True, "artifact_id": a["id"]}
                conn.exec_driver_sql("INSERT INTO export_job_artifacts VALUES (?,?)", (job_id, a["id"]))
                conn.exec_driver_sql(
                    "UPDATE jobs SET state='succeeded',result_json=?,updated_at=?,progress_done=progress_total WHERE id=?",
                    (canonical(result).decode(), timestamp(), job_id),
                )
                conn.exec_driver_sql(
                    "UPDATE export_artifacts SET last_access_at=? WHERE id=?", (timestamp(), a["id"])
                )
                self.srv.audit(
                    conn,
                    actor,
                    "working_export.reused",
                    job_id,
                    snapshot["project_id"],
                    {"artifact_id": a["id"]},
                    uid(),
                )
            return True

    @contextmanager
    def download(self, actor, job_id):
        with self.boundary.database(), self._download(actor, job_id) as stream:
            yield stream

    @contextmanager
    def _download(self, actor, job_id):
        with self.lock:
            with self.srv.db.engine.connect() as conn:
                job = row(conn, "SELECT * FROM jobs WHERE id=? AND type='working-export'", (job_id,))
                if not job:
                    raise Problem("NOT_FOUND", "Export not found.", 404)
                self.srv.maintain(conn, actor, job["project_id"])
                if job["state"] != "succeeded":
                    raise Problem("EXPORT_NOT_READY", "Export is not ready. Wait for completion.", 409)
                a = row(
                    conn,
                    "SELECT a.* FROM export_artifacts a JOIN export_job_artifacts l ON l.artifact_id=a.id WHERE l.job_id=?",
                    (job_id,),
                )
            ident = a["id"] if a else job_id
            if a and a["state"] != "ACTIVE":
                raise Problem(
                    "EXPORT_EXPIRED",
                    "Archive removed from cache. Prepare a new export from this snapshot or checkpoint.",
                    410,
                )
            self.active[ident] = self.active.get(ident, 0) + 1
        success = False
        try:
            path = a["path"] if a else f"export-cache/{job_id}.zip"
            try:
                with self.boundary.open_read(path) as stream:
                    import hashlib

                    if (
                        hashlib.file_digest(stream, "sha256").hexdigest()
                        != json.loads(job["result_json"])["sha256"]
                    ):
                        raise Problem(
                            "CORRUPT_EXPORT", "Archive checksum mismatch. Prepare another export.", 503
                        )
                    stream.seek(0)
                    yield stream
                    success = True
            except FileNotFoundError as exc:
                raise Problem(
                    "EXPORT_EXPIRED",
                    "Cached archive unavailable. Prepare a new export from the snapshot.",
                    410,
                ) from exc
        finally:
            with self.lock:
                self.active[ident] -= 1
                if success and a:
                    with self.srv.db.transaction() as conn:
                        conn.exec_driver_sql(
                            "UPDATE export_artifacts SET last_access_at=? WHERE id=?", (timestamp(), ident)
                        )

    def periodic(self):
        while not self.srv.stop.is_set():
            try:
                self.maintain()
            except Exception as exc:
                self.last_error = str(exc)
            if self.srv.stop.wait(900):
                break

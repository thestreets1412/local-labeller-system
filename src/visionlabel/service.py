import base64
import hashlib
import hmac
import json
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

from .database import Database, row, rows
from .domain import Problem, canonical, digest, empty_content, uid, validate_content
from .imaging import (
    IMAGE_EXTENSIONS,
    IMAGE_MIME,
    DecoderSession,
    exif_orientation,
    image_header,
    inspect_image,
)
from .legacy import parse_yolo
from .operations import DirectoryLock
from .statistics import summarize
from .storage import BlobStore, contained, local_directory


def now():
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def after(seconds):
    return (
        (datetime.now(UTC) + timedelta(seconds=seconds))
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()
    return salt + ":" + value


class Service:
    def __init__(self, root: Path):
        self.root = local_directory(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.directory_lock = DirectoryLock(self.root)
        self.inbox = self.root / "inbox"
        self.inbox.mkdir(exist_ok=True)
        self.db = Database(self.root / "db" / "data_tracking.sqlite3")
        self.db.migrate()
        self.blobs = BlobStore(self.root / "managed")
        keyfile = self.root / "claim.key"
        if not keyfile.exists():
            with keyfile.open("xb") as stream:
                stream.write(secrets.token_bytes(32))
                stream.flush()
                import os

                os.fsync(stream.fileno())
        self.key = keyfile.read_bytes()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="import")
        self.stop = threading.Event()
        self.fault = lambda point: None
        with self.db.transaction() as conn:
            conn.exec_driver_sql("UPDATE task_claims SET generation=generation+1,expires_at=?", (now(),))
            conn.exec_driver_sql(
                "UPDATE jobs SET state='failed',error_json=?,updated_at=? WHERE state IN ('queued','running')",
                (
                    json.dumps(
                        {
                            "code": "SERVER_RESTARTED",
                            "message": "Job interrupted. Inspect results and start a new request.",
                        }
                    ),
                    now(),
                ),
            )

    def close(self):
        self.stop.set()
        self.pool.shutdown(wait=True)
        self.db.engine.dispose()
        self.directory_lock.close()

    def bootstrap(self, username, password):
        if len(password) < 12:
            raise Problem("WEAK_PASSWORD", "Use a password with at least 12 characters.")
        hashed = password_hash(password)
        with self.db.transaction() as conn:
            if row(conn, "SELECT id FROM users LIMIT 1"):
                raise Problem("ALREADY_INITIALIZED", "An administrator already exists.", 409)
            user_id = uid()
            conn.exec_driver_sql(
                "INSERT INTO users (id,username,display_name,password_hash,is_admin,created_at) VALUES (?,?,?,?,1,?)",
                (user_id, username.casefold(), username, hashed, now()),
            )
        return user_id

    def login(self, username, password):
        with self.db.engine.connect() as conn:
            user = row(conn, "SELECT * FROM users WHERE username=? AND disabled=0", (username.casefold(),))
        stored = user["password_hash"] if user else "00" * 16 + ":" + "00" * 64
        if not hmac.compare_digest(password_hash(password, stored.split(":")[0]), stored) or not user:
            raise Problem("AUTH_REQUIRED", "Incorrect username or password.", 401)
        token, expires = secrets.token_urlsafe(32), after(8 * 3600)
        with self.db.transaction() as conn:
            current = row(conn, "SELECT * FROM users WHERE id=? AND disabled=0", (user["id"],))
            if not current or current["password_hash"] != stored:
                raise Problem("AUTH_REQUIRED", "Account changed. Sign in again.", 401)
            conn.exec_driver_sql(
                "INSERT INTO auth_tokens VALUES (?,?,?,?,NULL,?)",
                (uid(), user["id"], digest(token.encode()), expires, now()),
            )
        return {
            "token": token,
            "expires_at": expires,
            "user": {"id": user["id"], "username": user["username"]},
        }

    def authenticate(self, token):
        with self.db.engine.connect() as conn:
            user = row(
                conn,
                "SELECT u.id,u.username,u.is_admin,u.disabled FROM auth_tokens t JOIN users u ON t.user_id=u.id WHERE t.token_hash=? AND t.revoked_at IS NULL AND t.expires_at>? AND u.disabled=0",
                (digest(token.encode()), now()),
            )
        if not user:
            raise Problem("AUTH_REQUIRED", "Sign in to continue.", 401)
        user["_token_hash"] = digest(token.encode())
        return user

    def principal(self, conn, user):
        if user.get("_token_hash") and not row(
            conn,
            "SELECT id FROM auth_tokens WHERE token_hash=? AND user_id=? AND revoked_at IS NULL AND expires_at>?",
            (user["_token_hash"], user["id"], now()),
        ):
            raise Problem("AUTH_REQUIRED", "Session expired or was revoked.", 401)
        current = row(conn, "SELECT * FROM users WHERE id=? AND disabled=0", (user["id"],))
        if not current:
            raise Problem("AUTH_REQUIRED", "Account is unavailable. Sign in again.", 401)
        return current

    def administrator(self, conn, user):
        current = self.principal(conn, user)
        if not current["is_admin"]:
            raise Problem("FORBIDDEN", "Administrator permission is required.", 403)
        return current

    @staticmethod
    def public_user(record):
        return {
            k: record[k] for k in ("id", "username", "display_name", "is_admin", "disabled", "user_revision")
        }

    def secret_request(self, body):
        # Idempotency must not leave a fast offline password verifier in the DB.
        safe = dict(body)
        if safe.get("password") is not None:
            safe["password"] = hmac.new(self.key, safe["password"].encode(), hashlib.sha256).hexdigest()
        return safe

    def create_user(self, user, body, key, request_id):
        if not body["display_name"].strip():
            raise Problem("VALIDATION_FAILED", "Display name must not be blank.")
        safe = self.secret_request(body)
        with self.db.engine.connect() as conn:
            self.administrator(conn, user)
        hashed = password_hash(body["password"])
        with self.db.transaction() as conn:
            self.administrator(conn, user)
            replay = self.replay(conn, user, "users/create", key, safe)
            if replay:
                return replay
            username = body["username"].casefold()
            if row(conn, "SELECT id FROM users WHERE username=?", (username,)):
                raise Problem("USER_EXISTS", "Username already exists.", 409)
            ident = uid()
            conn.exec_driver_sql(
                "INSERT INTO users (id,username,display_name,password_hash,is_admin,created_at) VALUES (?,?,?,?,0,?)",
                (ident, username, body["display_name"].strip(), hashed, now()),
            )
            result = self.public_user(row(conn, "SELECT * FROM users WHERE id=?", (ident,)))
            self.audit(
                conn, user, "user.created", ident, detail={"username": username}, request_id=request_id
            )
            self.remember(conn, user, "users/create", key, safe, result, 201)
            return result

    def update_user(self, user, user_id, body, key, request_id):
        route, safe = f"users/update/{user_id}", self.secret_request(body)
        with self.db.engine.connect() as conn:
            self.administrator(conn, user)
        hashed = password_hash(body["password"]) if body.get("password") else None
        with self.db.transaction() as conn:
            self.administrator(conn, user)
            replay = self.replay(conn, user, route, key, safe)
            if replay:
                return replay
            target = row(conn, "SELECT * FROM users WHERE id=?", (user_id,))
            if not target:
                raise Problem("NOT_FOUND", "User not found.", 404)
            if target["user_revision"] != body["expected_user_revision"]:
                raise Problem("REVISION_CONFLICT", "Account changed. Refresh before editing.", 409)
            name = body.get("display_name")
            if name is not None and not name.strip():
                raise Problem("VALIDATION_FAILED", "Display name must not be blank.")
            disabled = target["disabled"] if body.get("disabled") is None else int(body["disabled"])
            if disabled:
                if target["is_admin"] and not row(
                    conn, "SELECT id FROM users WHERE is_admin=1 AND disabled=0 AND id<>?", (user_id,)
                ):
                    raise Problem("LAST_ADMIN", "The last active administrator cannot be disabled.", 409)
                stranded = row(
                    conn,
                    "SELECT m.project_id FROM project_members m WHERE m.user_id=? AND m.role='maintainer' AND NOT EXISTS (SELECT 1 FROM project_members other JOIN users u ON u.id=other.user_id WHERE other.project_id=m.project_id AND other.role='maintainer' AND u.disabled=0 AND other.user_id<>?)",
                    (user_id, user_id),
                )
                if stranded:
                    raise Problem(
                        "LAST_MAINTAINER",
                        "Assign another active maintainer before disabling this account.",
                        409,
                    )
            conn.exec_driver_sql(
                "UPDATE users SET display_name=?,disabled=?,password_hash=?,user_revision=user_revision+1 WHERE id=?",
                (
                    name.strip() if name is not None else target["display_name"],
                    disabled,
                    hashed or target["password_hash"],
                    user_id,
                ),
            )
            revoke = bool(disabled or hashed or body.get("revoke_sessions"))
            if revoke:
                conn.exec_driver_sql(
                    "UPDATE auth_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                    (now(), user_id),
                )
                conn.exec_driver_sql(
                    "UPDATE task_claims SET expires_at=?,generation=generation+1 WHERE owner_id=?",
                    (now(), user_id),
                )
            result = self.public_user(row(conn, "SELECT * FROM users WHERE id=?", (user_id,)))
            self.audit(
                conn,
                user,
                "user.updated",
                user_id,
                detail={
                    "disabled": bool(disabled),
                    "password_reset": bool(hashed),
                    "sessions_revoked": revoke,
                    "user_revision": result["user_revision"],
                },
                request_id=request_id,
            )
            self.remember(conn, user, route, key, safe, result)
            return result

    def change_member(self, user, project_id, user_id, body, key, request_id, remove=False):
        route = f"members/{'remove' if remove else 'set'}/{project_id}/{user_id}"
        with self.db.transaction() as conn:
            project = self.maintain(conn, user, project_id)
            replay = self.replay(conn, user, route, key, body)
            if replay:
                return replay
            if project["project_revision"] != body["expected_project_revision"]:
                raise Problem("REVISION_CONFLICT", "Project membership changed. Refresh before editing.", 409)
            target = row(conn, "SELECT * FROM users WHERE id=?", (user_id,))
            if not target:
                raise Problem("NOT_FOUND", "User not found.", 404)
            if target["disabled"] and not remove:
                raise Problem("VALIDATION_FAILED", "Enable the account before assigning a role.")
            previous = row(
                conn,
                "SELECT role FROM project_members WHERE project_id=? AND user_id=?",
                (project_id, user_id),
            )
            role = None if remove else body["role"]
            if previous and previous["role"] == "maintainer" and role != "maintainer":
                if not row(
                    conn,
                    "SELECT m.user_id FROM project_members m JOIN users u ON u.id=m.user_id WHERE m.project_id=? AND m.role='maintainer' AND m.user_id<>? AND u.disabled=0",
                    (project_id, user_id),
                ):
                    raise Problem(
                        "LAST_MAINTAINER",
                        "The last active project maintainer cannot be removed or demoted.",
                        409,
                    )
            if remove:
                conn.exec_driver_sql(
                    "DELETE FROM project_members WHERE project_id=? AND user_id=?", (project_id, user_id)
                )
            else:
                conn.exec_driver_sql(
                    "INSERT INTO project_members VALUES (?,?,?) ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role",
                    (project_id, user_id, role),
                )
            conn.exec_driver_sql(
                "UPDATE task_claims SET expires_at=?,generation=generation+1 WHERE owner_id=? AND image_id IN (SELECT id FROM images WHERE project_id=?)",
                (now(), user_id, project_id),
            )
            conn.exec_driver_sql(
                "UPDATE projects SET project_revision=project_revision+1 WHERE id=?", (project_id,)
            )
            result = {"user_id": user_id, "role": role, "project_revision": project["project_revision"] + 1}
            self.audit(
                conn,
                user,
                "membership.removed" if remove else "membership.updated",
                user_id,
                project_id,
                {"previous_role": previous["role"] if previous else None, **result},
                request_id,
            )
            self.remember(conn, user, route, key, body, result, 204 if remove else 200)
            return result

    def authorize(self, conn, user, project_id, write=False):
        current = self.principal(conn, user)
        project = row(conn, "SELECT * FROM projects WHERE id=?", (project_id,))
        member = row(
            conn,
            "SELECT role FROM project_members WHERE project_id=? AND user_id=?",
            (project_id, user["id"]),
        )
        if not current or not project or (not current["is_admin"] and not member):
            raise Problem("NOT_FOUND", "Project not found.", 404)
        if write and not current["is_admin"] and member["role"] == "viewer":
            raise Problem("FORBIDDEN", "This account cannot edit the project.", 403)
        return project

    def maintain(self, conn, user, project_id):
        project = self.authorize(conn, user, project_id, True)
        current = row(conn, "SELECT is_admin FROM users WHERE id=?", (user["id"],))
        member = row(
            conn,
            "SELECT role FROM project_members WHERE project_id=? AND user_id=?",
            (project_id, user["id"]),
        )
        if not current["is_admin"] and (not member or member["role"] != "maintainer"):
            raise Problem("FORBIDDEN", "Maintainer permission is required.", 403)
        return project

    def audit(self, conn, user, action, entity, project=None, detail=None, request_id="internal"):
        conn.exec_driver_sql(
            "INSERT INTO audit_events VALUES (?,?,?,?,?,?,?,?)",
            (uid(), project, user["id"], action, entity, request_id, canonical(detail or {}).decode(), now()),
        )

    def replay(self, conn, user, route, key, body):
        if not key or len(key) > 200:
            raise Problem("VALIDATION_FAILED", "A valid Idempotency-Key header is required.")
        request_hash = digest(canonical(body))
        record = row(
            conn,
            "SELECT * FROM idempotency_records WHERE user_id=? AND route_scope=? AND key=?",
            (user["id"], route, key),
        )
        if record and record["request_sha256"] != request_hash:
            raise Problem("IDEMPOTENCY_KEY_REUSED", "This key was already used for a different request.", 409)
        return json.loads(record["response_json"]) if record else None

    def remember(self, conn, user, route, key, body, result, status=200):
        conn.exec_driver_sql(
            "INSERT INTO idempotency_records VALUES (?,?,?,?,?,?,?)",
            (user["id"], route, key, digest(canonical(body)), canonical(result).decode(), status, now()),
        )

    def create_project(self, user, body, key, request_id):
        classes = [name.strip() for name in body["initial_classes"]]
        if any(not name or len(name) > 100 for name in classes) or len(
            {x.casefold() for x in classes}
        ) != len(classes):
            raise Problem("VALIDATION_FAILED", "Class names must be nonempty and unique.")
        with self.db.engine.connect() as conn:
            current = self.principal(conn, user)
            if not current["is_admin"] and not row(
                conn,
                "SELECT project_id FROM project_members WHERE user_id=? AND role='maintainer'",
                (user["id"],),
            ):
                raise Problem("FORBIDDEN", "Project creation requires a maintainer or admin.", 403)
            replay = self.replay(conn, user, "projects", key, body)
            if replay:
                self.authorize(conn, user, replay["id"])
                return replay
        project_id, schema_id = uid(), uid()
        colors = ["#4CC9A6", "#FFB454", "#68A8FF", "#E989B9", "#B0A0FF", "#E8CF65"]
        entries = [
            {
                "class_id": uid(),
                "display_name": name,
                "stable_key": f"class_{i}",
                "export_index": i,
                "color_hex": colors[i % len(colors)],
                "active": True,
            }
            for i, name in enumerate(classes)
        ]
        schema = {"id": schema_id, "project_id": project_id, "number": 1, "entries": entries}
        data = canonical(schema)
        path = f"projects/{project_id}/schemas/{schema_id}.json"
        self.blobs.publish(path, data)
        with self.db.transaction() as conn:
            current = self.principal(conn, user)
            if not current["is_admin"] and not row(
                conn,
                "SELECT project_id FROM project_members WHERE user_id=? AND role='maintainer'",
                (user["id"],),
            ):
                raise Problem("FORBIDDEN", "Project creation requires a maintainer or admin.", 403)
            replay = self.replay(conn, user, "projects", key, body)
            if replay:
                self.authorize(conn, user, replay["id"])
                return replay
            if row(conn, "SELECT id FROM projects WHERE slug=?", (body["slug"],)):
                raise Problem("PROJECT_EXISTS", "Project slug already exists.", 409)
            conn.exec_driver_sql(
                "INSERT INTO projects (id,slug,name,task_type,created_at,created_by) VALUES (?,?,?,?,?,?)",
                (project_id, body["slug"], body["name"], body["task_type"], now(), user["id"]),
            )
            conn.exec_driver_sql(
                "INSERT INTO class_schemas VALUES (?,?,?,?,?,?,?)",
                (schema_id, project_id, 1, path, digest(data), now(), user["id"]),
            )
            for entry in entries:
                conn.exec_driver_sql(
                    "INSERT INTO classes VALUES (?,?,?)", (entry["class_id"], project_id, entry["stable_key"])
                )
                conn.exec_driver_sql(
                    "INSERT INTO class_schema_entries VALUES (?,?,?,?,?,1)",
                    (
                        schema_id,
                        entry["class_id"],
                        entry["display_name"],
                        entry["export_index"],
                        entry["color_hex"],
                    ),
                )
            conn.exec_driver_sql("UPDATE projects SET active_schema_id=? WHERE id=?", (schema_id, project_id))
            conn.exec_driver_sql(
                "INSERT INTO project_members VALUES (?,?,'maintainer')", (project_id, user["id"])
            )
            result = dict(row(conn, "SELECT * FROM projects WHERE id=?", (project_id,)), schema=schema)
            self.audit(conn, user, "project.created", project_id, project_id, request_id=request_id)
            self.remember(conn, user, "projects", key, body, result, 201)
        return result

    def project(self, user, project_id):
        with self.db.engine.connect() as conn:
            project = self.authorize(conn, user, project_id)
            current = self.principal(conn, user)
            member = row(
                conn,
                "SELECT role FROM project_members WHERE project_id=? AND user_id=?",
                (project_id, user["id"]),
            )
            role = member["role"] if member else None
            project["can_edit"] = bool(current["is_admin"] or role in ("annotator", "reviewer", "maintainer"))
            project["can_manage_members"] = bool(current["is_admin"] or role == "maintainer")
            schema = row(conn, "SELECT * FROM class_schemas WHERE id=?", (project["active_schema_id"],))
        project["schema"] = self.blobs.json(schema["blob_path"], schema["sha256"])
        return project

    def image(self, conn, user, image_id, write=False):
        image = row(
            conn,
            "SELECT i.*,a.width,a.height,a.blob_path,a.media_type,a.extension,h.current_revision,h.state_revision,h.status FROM images i JOIN assets a ON a.sha256=i.asset_sha256 JOIN annotation_heads h ON h.image_id=i.id WHERE i.id=? AND i.archived=0",
            (image_id,),
        )
        if not image:
            raise Problem("NOT_FOUND", "Image not found.", 404)
        self.authorize(conn, user, image["project_id"], write)
        return image

    def annotation(self, user, image_id):
        with self.db.engine.connect() as conn:
            image = self.image(conn, user, image_id)
            revision = row(
                conn,
                "SELECT * FROM annotation_revisions WHERE image_id=? AND revision=?",
                (image_id, image["current_revision"]),
            )
        return {
            "annotation": self.blobs.json(revision["blob_path"], revision["sha256"]) if revision else None,
            "annotation_sha256": revision["sha256"] if revision else None,
            "revision": image["current_revision"],
            "state_revision": image["state_revision"],
            "status": image["status"],
        }

    def statistics(self, user, project_id):
        with self.db.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN")
            project = self.authorize(conn, user, project_id)
            entries = rows(
                conn,
                "SELECT * FROM class_schema_entries WHERE schema_id=? ORDER BY class_id",
                (project["active_schema_id"],),
            )
            records = rows(
                conn,
                "SELECT i.*,a.width,a.height,a.media_type,h.status,h.current_revision,h.state_revision,r.blob_path AS annotation_path,r.sha256 AS annotation_hash FROM images i JOIN assets a ON a.sha256=i.asset_sha256 JOIN annotation_heads h ON h.image_id=i.id LEFT JOIN annotation_revisions r ON r.image_id=i.id AND r.revision=h.current_revision WHERE i.project_id=? AND i.archived=0 ORDER BY i.id",
                (project_id,),
            )
        images = []
        for record in records:
            if record["current_revision"] and not record["annotation_path"]:
                raise Problem("CORRUPT_DATABASE", "A saved annotation reference is missing.", 503)
            annotation = (
                self.blobs.json(record["annotation_path"], record["annotation_hash"])
                if record["annotation_path"]
                else None
            )
            images.append((record, annotation))
        signature = {
            "schema_id": project["active_schema_id"],
            "project_revision": project["project_revision"],
            "images": [
                {
                    k: item[k]
                    for k in (
                        "id",
                        "asset_sha256",
                        "group_key",
                        "display_filename",
                        "current_revision",
                        "state_revision",
                        "annotation_hash",
                    )
                }
                for item in records
            ],
        }
        return dict(
            summarize(images, entries),
            scope="working",
            project_id=project_id,
            project_revision=project["project_revision"],
            source_revision=digest(canonical(signature)),
            generated_at=now(),
        )

    def claim_token(self, claim_id, generation):
        return hmac.new(self.key, f"{claim_id}:{generation}".encode(), hashlib.sha256).hexdigest()

    def claim(self, user, image_id, body, key, request_id):
        route = f"claim/{image_id}"
        with self.db.transaction() as conn:
            image = self.image(conn, user, image_id, True)
            replay = self.replay(conn, user, route, key, body)
            if replay:
                replay["claim_token"] = self.claim_token(replay["claim_id"], replay["generation"])
                return replay
            if image["status"] not in ("UNLABELED", "IN_PROGRESS", "ANNOTATED", "REJECTED"):
                raise Problem("STATE_CONFLICT", "Image is not editable.", 409)
            existing = row(conn, "SELECT * FROM task_claims WHERE image_id=?", (image_id,))
            if existing and existing["expires_at"] > now():
                raise Problem("CLAIMED_BY_OTHER", "This image already has an active editing session.", 423)
            generation = existing["generation"] + 1 if existing else 1
            claim_id, expires = uid(), after(900)
            token = self.claim_token(claim_id, generation)
            conn.exec_driver_sql(
                "INSERT INTO task_claims VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(image_id) DO UPDATE SET claim_id=excluded.claim_id,owner_id=excluded.owner_id,client_instance_id=excluded.client_instance_id,generation=excluded.generation,token_hash=excluded.token_hash,expires_at=excluded.expires_at,last_heartbeat_at=excluded.last_heartbeat_at",
                (
                    image_id,
                    claim_id,
                    user["id"],
                    body["client_instance_id"],
                    generation,
                    digest(token.encode()),
                    expires,
                    now(),
                ),
            )
            result = {
                "claim_id": claim_id,
                "generation": generation,
                "mode": "edit",
                "owner_id": user["id"],
                "server_time": now(),
                "expires_at": expires,
                "heartbeat_interval_seconds": 45,
            }
            self.remember(conn, user, route, key, body, result, 201)
            self.audit(conn, user, "claim.acquired", image_id, image["project_id"], request_id=request_id)
        return dict(result, claim_token=token)

    def check_claim(self, conn, user, image_id, headers):
        claim = row(conn, "SELECT * FROM task_claims WHERE image_id=?", (image_id,))
        if not claim or claim["expires_at"] <= now():
            raise Problem("LEASE_EXPIRED", "Editing lease expired. Reload and acquire a new lease.", 409)
        if (
            claim["owner_id"] != user["id"]
            or claim["claim_id"] != headers.get("id")
            or str(claim["generation"]) != str(headers.get("generation"))
            or not hmac.compare_digest(claim["token_hash"], digest(headers.get("token", "").encode()))
        ):
            raise Problem("LEASE_REVOKED", "Editing lease is no longer valid.", 409)
        return claim

    def heartbeat(self, user, image_id, headers):
        with self.db.transaction() as conn:
            self.image(conn, user, image_id, True)
            self.check_claim(conn, user, image_id, headers)
            expires = after(900)
            conn.exec_driver_sql(
                "UPDATE task_claims SET expires_at=?,last_heartbeat_at=? WHERE image_id=?",
                (expires, now(), image_id),
            )
        return {"expires_at": expires, "server_time": now()}

    def release(self, user, image_id, headers, request_id):
        with self.db.transaction() as conn:
            image = self.image(conn, user, image_id, True)
            claim = row(conn, "SELECT * FROM task_claims WHERE image_id=?", (image_id,))
            if (
                claim
                and claim["claim_id"] == headers.get("id")
                and claim["owner_id"] == user["id"]
                and claim["expires_at"] <= now()
                and hmac.compare_digest(claim["token_hash"], digest(headers.get("token", "").encode()))
            ):
                return
            self.check_claim(conn, user, image_id, headers)
            conn.exec_driver_sql(
                "UPDATE task_claims SET expires_at=?,generation=generation+1 WHERE image_id=?",
                (now(), image_id),
            )
            self.audit(conn, user, "claim.released", image_id, image["project_id"], request_id=request_id)

    def save(self, user, image_id, body, headers, key, request_id, import_provenance=None):
        route = f"save/{image_id}"

        def preflight(conn):
            image = self.image(conn, user, image_id, True)
            if import_provenance is not None:
                self.maintain(conn, user, image["project_id"])
                if image["current_revision"] != 0:
                    raise Problem(
                        "ANNOTATION_EXISTS", "Predictions cannot overwrite existing annotations.", 409
                    )
            replay = self.replay(conn, user, route, key, body)
            if replay:
                return image, None, replay
            self.check_claim(conn, user, image_id, headers)
            if (
                image["current_revision"] != body["expected_revision"]
                or image["state_revision"] != body["expected_state_revision"]
            ):
                raise Problem(
                    "REVISION_CONFLICT",
                    "The server revision changed. Compare your draft before saving.",
                    409,
                    current_revision=image["current_revision"],
                    current_state_revision=image["state_revision"],
                )
            project = self.authorize(conn, user, image["project_id"], True)
            if project["active_schema_id"] != body["class_schema_id"]:
                raise Problem("SCHEMA_CHANGED", "The class schema changed. Reload the project.", 409)
            if image["status"] not in ("UNLABELED", "IN_PROGRESS", "REJECTED"):
                raise Problem("STATE_CONFLICT", "Resume or reopen this image before editing.", 409)
            class_ids = {
                x["class_id"]
                for x in rows(
                    conn,
                    "SELECT class_id FROM class_schema_entries WHERE schema_id=? AND active=1",
                    (body["class_schema_id"],),
                )
            }
            content = validate_content(
                body["content"], image["width"], image["height"], project["task_type"], class_ids
            )
            return image, content, None

        with self.db.engine.connect() as conn:
            image, content, replay = preflight(conn)
        if replay:
            return replay
        revision = image["current_revision"] + 1
        timestamp = now()
        doc = dict(
            content,
            schema_version="1.0.0",
            project_id=image["project_id"],
            image_id=image_id,
            asset_sha256=image["asset_sha256"],
            width=image["width"],
            height=image["height"],
            class_schema_id=body["class_schema_id"],
            revision=revision,
            created_by=user["id"],
            created_at=timestamp,
        )
        data = canonical(doc)
        sha = digest(data)
        path = f"projects/{image['project_id']}/annotations/{image_id}/r{revision:08d}-{sha}.json"
        self.fault("before_publish")
        self.blobs.publish(path, data)
        self.fault("after_publish")
        with self.db.transaction() as conn:
            image, content, replay = preflight(conn)
            if replay:
                return replay
            self.blobs.read(path, sha)
            conn.exec_driver_sql(
                "INSERT INTO annotation_revisions VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    image_id,
                    revision,
                    body["class_schema_id"],
                    path,
                    sha,
                    int(content["verified_empty"]),
                    len(content["shapes"]),
                    timestamp,
                    user["id"],
                ),
            )
            changed = conn.exec_driver_sql(
                "UPDATE annotation_heads SET current_revision=?,state_revision=state_revision+1,status='IN_PROGRESS',updated_at=? WHERE image_id=? AND current_revision=? AND state_revision=?",
                (revision, timestamp, image_id, body["expected_revision"], body["expected_state_revision"]),
            )
            if changed.rowcount != 1:
                raise Problem("REVISION_CONFLICT", "The revision changed.", 409)
            result = {
                "image_id": image_id,
                "revision": revision,
                "state_revision": image["state_revision"] + 1,
                "status": "IN_PROGRESS",
                "annotation_sha256": sha,
                "saved_at": timestamp,
            }
            previous = row(
                conn,
                "SELECT * FROM annotation_revisions WHERE image_id=? AND revision=?",
                (image_id, revision - 1),
            )
            old = self.blobs.json(previous["blob_path"], previous["sha256"]) if previous else empty_content()
            before = {s["id"]: s for s in old["shapes"]}
            current = {s["id"]: s for s in content["shapes"]}
            detail = {
                "revision": revision,
                "sha256": sha,
                "created": sorted(current.keys() - before.keys()),
                "deleted": sorted(before.keys() - current.keys()),
                "updated": sorted(k for k in current.keys() & before.keys() if current[k] != before[k]),
                "image_labels_changed": old["image_labels"] != content["image_labels"],
            }
            if import_provenance is not None:
                detail["import"] = import_provenance
            self.audit(conn, user, "annotation.saved", image_id, image["project_id"], detail, request_id)
            self.remember(conn, user, route, key, body, result)
            self.fault("before_commit")
        self.fault("after_commit")
        return result

    def import_images(self, user, project_id, body, key, request_id):
        route = f"import/{project_id}"
        with self.db.transaction() as conn:
            self.maintain(conn, user, project_id)
            if body.get("yolo"):
                self.check_yolo_import(conn, user, project_id, body["yolo"])
            replay = self.replay(conn, user, route, key, body)
            if replay:
                return replay
            job_id = uid()
            conn.exec_driver_sql(
                "INSERT INTO jobs (id,project_id,created_by,type,state,payload_json,progress_total,created_at,updated_at) VALUES (?,?,?,'import','queued',?,?,?,?)",
                (
                    job_id,
                    project_id,
                    user["id"],
                    canonical(body).decode(),
                    len(body["relative_paths"]),
                    now(),
                    now(),
                ),
            )
            result = {"job_id": job_id}
            self.remember(conn, user, route, key, body, result, 202)
        self.pool.submit(self.run_import, user, project_id, job_id, body, request_id)
        return result

    def run_import(self, user, project_id, job_id, body, request_id):
        results = []
        decoder = DecoderSession()
        try:
            with self.db.transaction() as conn:
                conn.exec_driver_sql(
                    "UPDATE jobs SET state='running',updated_at=? WHERE id=?", (now(), job_id)
                )
            for rel in body["relative_paths"]:
                if self.stop.is_set():
                    raise Problem("SERVER_STOPPING", "Import stopped during server shutdown.", 503)
                try:
                    results.append(
                        self.ingest(
                            user,
                            project_id,
                            job_id,
                            rel,
                            body["dry_run"],
                            request_id,
                            decoder,
                            body.get("yolo"),
                        )
                    )
                except (Problem, OSError) as exc:
                    results.append(
                        {
                            "path": rel,
                            "outcome": "invalid",
                            "code": exc.code if isinstance(exc, Problem) else "STORAGE_UNAVAILABLE",
                            "message": exc.message if isinstance(exc, Problem) else "File could not be read.",
                            "details": exc.details if isinstance(exc, Problem) else {},
                        }
                    )
                with self.db.transaction() as conn:
                    conn.exec_driver_sql(
                        "UPDATE jobs SET progress_done=?,result_json=?,updated_at=? WHERE id=?",
                        (len(results), canonical({"items": results}).decode(), now(), job_id),
                    )
            with self.db.transaction() as conn:
                self.maintain(conn, user, project_id)
                conn.exec_driver_sql(
                    "UPDATE jobs SET state='succeeded',updated_at=? WHERE id=?", (now(), job_id)
                )
        except Exception as exc:
            error = {
                "code": exc.code if isinstance(exc, Problem) else "IMPORT_FAILED",
                "message": exc.message
                if isinstance(exc, Problem)
                else "Import failed. See the local operator log.",
            }
            with self.db.transaction() as conn:
                conn.exec_driver_sql(
                    "UPDATE jobs SET state='failed',error_json=?,updated_at=? WHERE id=?",
                    (canonical(error).decode(), now(), job_id),
                )
        finally:
            decoder.close()

    def check_yolo_import(self, conn, user, project_id, options):
        project = self.maintain(conn, user, project_id)
        if project["task_type"] != "detection":
            raise Problem("INVALID_TASK", "YOLO rectangle import requires a detection project.")
        if project["active_schema_id"] != options["class_schema_id"]:
            raise Problem("SCHEMA_CHANGED", "Reload the project and class mapping.", 409)
        allowed = {
            r["class_id"]
            for r in rows(
                conn,
                "SELECT class_id FROM class_schema_entries WHERE schema_id=? AND active=1",
                (options["class_schema_id"],),
            )
        }
        mapping = options["class_mapping"]
        if not mapping or any(
            not k.isascii() or not k.isdecimal() or str(int(k)) != k or v not in allowed
            for k, v in mapping.items()
        ):
            raise Problem("INVALID_MAPPING", "Map each YOLO integer class index to an active project class.")

    def ingest(self, user, project_id, job_id, relative, dry_run, request_id, decoder=None, yolo=None):
        source = contained(self.inbox, relative, True)
        if source.suffix.lower() not in IMAGE_EXTENSIONS:
            raise Problem("INVALID_IMAGE", "Supported image formats: PNG, JPEG and BMP.")
        stat = source.stat()
        if stat.st_size > 50 * 1024 * 1024:
            raise Problem("INVALID_IMAGE", "Image exceeds 50 MiB.")
        with source.open("rb") as stream:
            data = stream.read(50 * 1024 * 1024 + 1)
        if source.stat().st_mtime_ns != stat.st_mtime_ns or source.stat().st_size != stat.st_size:
            raise Problem("SOURCE_CHANGED", "Source changed while importing. Retry after the copy finishes.")
        width, height, extension = image_header(data)
        sha = digest(data)
        candidate = None
        label_sha = None
        label_relative = None
        label_state = None
        if yolo:
            with self.db.engine.connect() as conn:
                self.check_yolo_import(conn, user, project_id, yolo)
            siblings = [
                p
                for p in source.parent.iterdir()
                if p.stem.casefold() == source.stem.casefold()
                and p.suffix.lower() in IMAGE_EXTENSIONS
                and p.is_file()
            ]
            if len(siblings) != 1:
                raise Problem(
                    "AMBIGUOUS_PAIR",
                    "Multiple images share this filename stem. Rename image/label pairs before importing.",
                )
            if extension == "jpg" and exif_orientation(data) != 1:
                raise Problem(
                    "ORIENTATION_AMBIGUOUS",
                    "Resolve EXIF orientation with a new image before importing predictions.",
                )
            label_relative = str(Path(relative).with_suffix(".txt")).replace("\\", "/")
            label = contained(self.inbox, label_relative)
            raw_label = None
            if label.exists():
                label_stat = label.stat()
                with label.open("rb") as stream:
                    raw_label = stream.read(8 * 1024 * 1024 + 1)
                after_stat = label.stat()
                if (after_stat.st_mtime_ns, after_stat.st_size) != (
                    label_stat.st_mtime_ns,
                    label_stat.st_size,
                ):
                    raise Problem(
                        "SOURCE_CHANGED", "Label changed while importing. Retry after the copy finishes."
                    )
                if len(raw_label) > 8 * 1024 * 1024:
                    raise Problem("INVALID_LABEL", "YOLO label exceeds 8 MiB.")
                label_sha = digest(raw_label)
            try:
                candidate, label_state = parse_yolo(
                    raw_label.decode("utf-8-sig") if raw_label is not None else None,
                    width,
                    height,
                    yolo["class_mapping"],
                    source_identity=f"{sha}:{label_sha}",
                    empty_is_verified=yolo["empty_is_verified"],
                )
            except UnicodeError as exc:
                raise Problem("INVALID_LABEL", "YOLO text must be UTF-8.") from exc
        staging = self.root / f"decode-{uid()}.{extension}"
        try:
            staging.write_bytes(data)
            w, h = decoder.inspect(staging) if decoder else inspect_image(staging)
            assert (w, h) == (width, height)
        finally:
            staging.unlink(missing_ok=True)
        with self.db.engine.connect() as conn:
            self.maintain(conn, user, project_id)
            existing = row(
                conn, "SELECT id FROM images WHERE project_id=? AND asset_sha256=?", (project_id, sha)
            )
            if yolo and existing:
                head = self.image(conn, user, existing["id"], True)
                if head["current_revision"] != 0:
                    raise Problem(
                        "ANNOTATION_EXISTS",
                        "Predictions cannot overwrite existing annotations.",
                        409,
                        image_id=existing["id"],
                    )
        if dry_run:
            return {
                "path": relative,
                "outcome": "duplicate" if existing else "new",
                "asset_sha256": sha,
                "label_path": label_relative,
                "label_sha256": label_sha,
                "label_state": label_state,
                "shape_count": len(candidate["shapes"]) if candidate else 0,
            }
        path = f"assets/sha256/{sha[:2]}/{sha}.{extension}"
        self.blobs.publish(path, data)
        with self.db.transaction() as conn:
            self.maintain(conn, user, project_id)
            existing = row(
                conn, "SELECT id FROM images WHERE project_id=? AND asset_sha256=?", (project_id, sha)
            )
            image_id = existing["id"] if existing else uid()
            if not existing:
                conn.exec_driver_sql(
                    "INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        sha,
                        len(data),
                        IMAGE_MIME[extension],
                        extension,
                        width,
                        height,
                        path,
                        now(),
                        user["id"],
                    ),
                )
                conn.exec_driver_sql(
                    "INSERT INTO images (id,project_id,asset_sha256,display_filename,created_at,created_by) VALUES (?,?,?,?,?,?)",
                    (image_id, project_id, sha, source.name, now(), user["id"]),
                )
                conn.exec_driver_sql(
                    "INSERT INTO annotation_heads (image_id,updated_at) VALUES (?,?)", (image_id, now())
                )
            conn.exec_driver_sql(
                "INSERT INTO image_sources VALUES (?,?,?,?,?,?,?)",
                (uid(), image_id, job_id, "inbox", relative, sha, now()),
            )
            self.audit(
                conn,
                user,
                "image.imported",
                image_id,
                project_id,
                {"duplicate": bool(existing), "asset_sha256": sha},
                request_id,
            )
        result = {
            "path": relative,
            "outcome": "duplicate" if existing else "imported",
            "image_id": image_id,
            "warnings": ["EXIF rotation ignored; annotations use original raster coordinates."]
            if extension == "jpg" and exif_orientation(data) != 1
            else [],
        }
        if yolo:
            assert candidate is not None
            result.update(
                label_path=label_relative,
                label_sha256=label_sha,
                label_state="UNLABELED",
                shape_count=len(candidate["shapes"]),
            )
            if label_state == "UNLABELED":
                result["warnings"].append(
                    "Missing or empty label was left unlabeled; no prediction revision was created."
                )
                return result
            lease = None
            try:
                lease = self.claim(
                    user, image_id, {"mode": "edit", "client_instance_id": uid()}, uid(), request_id
                )
                headers = {
                    "id": lease["claim_id"],
                    "token": lease["claim_token"],
                    "generation": lease["generation"],
                }
                with self.db.engine.connect() as conn:
                    head = self.image(conn, user, image_id, True)
                saved = self.save(
                    user,
                    image_id,
                    {
                        "expected_revision": 0,
                        "expected_state_revision": head["state_revision"],
                        "class_schema_id": yolo["class_schema_id"],
                        "content": candidate,
                    },
                    headers,
                    uid(),
                    request_id,
                    import_provenance={
                        "format": "yolo-detection",
                        "job_id": job_id,
                        "label_path": label_relative,
                        "label_sha256": label_sha,
                        "asset_sha256": sha,
                        "options": yolo,
                    },
                )
                result.update(label_state=saved["status"], revision=saved["revision"])
            except (Problem, OSError) as exc:
                result.update(
                    outcome="invalid",
                    code=exc.code if isinstance(exc, Problem) else "STORAGE_UNAVAILABLE",
                    message=exc.message
                    if isinstance(exc, Problem)
                    else "Prediction save failed; the image was retained.",
                    label_state="NOT_IMPORTED",
                    image_retained=True,
                )
            finally:
                if lease:
                    try:
                        self.release(user, image_id, headers, request_id)
                    except Problem:
                        pass
        return result


def encode_cursor(created_at, entity_id, scope):
    return base64.urlsafe_b64encode(canonical([created_at, entity_id, scope])).decode()


def decode_cursor(value, scope):
    if not value:
        return "", ""
    try:
        created_at, entity_id, actual = json.loads(base64.urlsafe_b64decode(value))
        if actual != scope or not isinstance(created_at, str) or not isinstance(entity_id, str):
            raise ValueError
        return created_at, entity_id
    except Exception as exc:
        raise Problem("INVALID_CURSOR", "Invalid cursor or filters changed.", 400) from exc

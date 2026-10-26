"""Service-owned immutable checkpoints, schema changes and atomic working restore."""

import json
from collections import Counter
from copy import deepcopy
from typing import Literal

from pydantic import Field, StrictBool

from .checkpoint_domain import checkpoint_manifest, content_of, edited_schema, migrate_content, semantic_diff
from .contracts import StrictModel
from .database import row, rows
from .domain import Problem, canonical, digest, uid, validate_content
from .service import after, now


class ClassEdit(StrictModel):
    class_id: str | None = None
    display_name: str = Field(min_length=1, max_length=100)
    active: StrictBool = True


class PreviewRequest(StrictModel):
    kind: Literal["checkpoint", "schema", "restore"]
    label: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    checkpoint_id: str | None = None
    classes: list[ClassEdit] | None = Field(default=None, min_length=1, max_length=1000)
    mapping: dict[str, str | None] = Field(default_factory=dict, max_length=1000)


def capture(srv, conn, project):
    pid = project["id"]
    schema = row(conn, "SELECT * FROM class_schemas WHERE id=?", (project["active_schema_id"],))
    records = rows(
        conn,
        "SELECT i.id AS image_id,i.asset_sha256,i.display_filename,i.group_key,i.created_at,a.width,a.height,a.extension,a.blob_path AS asset_path,h.status,h.current_revision,h.state_revision,r.schema_id,r.blob_path AS annotation_path,r.sha256 AS annotation_sha256 FROM images i JOIN assets a ON a.sha256=i.asset_sha256 JOIN annotation_heads h ON h.image_id=i.id LEFT JOIN annotation_revisions r ON r.image_id=i.id AND r.revision=h.current_revision WHERE i.project_id=? AND i.archived=0 ORDER BY i.created_at,i.id",
        (pid,),
    )
    reviews = {
        r["image_id"]: r
        for r in rows(
            conn,
            "SELECT w.* FROM working_reviews w JOIN images i ON i.id=w.image_id JOIN annotation_heads h ON h.image_id=i.id AND h.state_revision=w.state_revision AND h.current_revision=w.annotation_revision WHERE i.project_id=? AND i.archived=0",
            (pid,),
        )
    }
    for record in records:
        review = reviews.get(record["image_id"])
        if review and (
            review["schema_id"] != record["schema_id"]
            or review["annotation_sha256"] != record["annotation_sha256"]
        ):
            raise Problem("INVALID_REVIEW", "Review evidence does not match the saved annotation.", 409)
        if record["status"] in ("REVIEWED_PASS", "REVIEWED_NG") and not review:
            raise Problem("INVALID_REVIEW", "Review evidence is missing.", 409)
        record["review"] = review
    return checkpoint_manifest(pid, project["task_type"], schema, records)


def checked_contents(srv, snapshot, assets=False, progress=None, phase="Verifying checkpoint files"):
    schema = srv.blobs.json(snapshot["schema"]["blob_path"], snapshot["schema"]["sha256"])
    if schema["id"] != snapshot["schema"]["id"] or schema["project_id"] != snapshot["project_id"]:
        raise Problem("CORRUPT_BLOB", "Checkpoint schema identity mismatch.", 503)
    classes = {e["class_id"] for e in schema["entries"] if e["active"]}
    contents = {}
    for position, record in enumerate(snapshot["records"]):
        if progress:
            progress(phase, position, len(snapshot["records"]))
        if srv.stop.is_set():
            raise Problem("SERVER_STOPPING", "Dataset operation interrupted; retry the preview.", 503)
        if assets:
            # Bounded streaming verification, including files excluded by training export.
            from .storage import contained
            from .working_export import file_hash

            try:
                path = contained(srv.blobs.root, record["asset_path"], exists=True)
                if file_hash(path) != record["asset_sha256"]:
                    raise Problem("CORRUPT_BLOB", "Checkpoint image checksum mismatch.", 503)
            except OSError as exc:
                raise Problem("STORAGE_UNAVAILABLE", "Checkpoint image unavailable.", 503) from exc
        doc = None
        if record["current_revision"]:
            doc = srv.blobs.json(record["annotation_path"], record["annotation_sha256"])
            expected = {
                "image_id": record["image_id"],
                "project_id": snapshot["project_id"],
                "revision": record["current_revision"],
                "asset_sha256": record["asset_sha256"],
                "class_schema_id": schema["id"],
                "width": record["width"],
                "height": record["height"],
            }
            if record["schema_id"] != schema["id"] or any(doc.get(k) != v for k, v in expected.items()):
                raise Problem("CORRUPT_BLOB", "Checkpoint annotation identity mismatch.", 503)
        contents[record["image_id"]] = validate_content(
            content_of(doc), record["width"], record["height"], snapshot["task_type"], classes
        )
    return contents


def get_checkpoint(srv, user, pid, ident, conn=None):
    if conn is None:
        with srv.db.engine.connect() as connection:
            return get_checkpoint(srv, user, pid, ident, connection)
    srv.authorize(conn, user, pid)
    checkpoint = row(conn, "SELECT * FROM dataset_checkpoints WHERE id=? AND project_id=?", (ident, pid))
    if not checkpoint:
        raise Problem("NOT_FOUND", "Checkpoint not found.", 404)
    snapshot = srv.blobs.json(checkpoint["blob_path"], checkpoint["sha256"])
    return checkpoint, snapshot


def list_checkpoints(srv, user, pid, before=2147483647, limit=50):
    with srv.db.engine.connect() as conn:
        srv.authorize(conn, user, pid)
        items = rows(
            conn,
            "SELECT c.*,u.display_name AS author FROM dataset_checkpoints c JOIN users u ON u.id=c.created_by WHERE project_id=? AND sequence<? ORDER BY sequence DESC LIMIT ?",
            (pid, before, limit + 1),
        )
    page = items[:limit]
    return {"items": page, "next_before": page[-1]["sequence"] if len(items) > limit else None}


def preview(srv, user, pid, body, key, request_id):
    body = PreviewRequest.model_validate(body).model_dump()
    body["label"], body["message"] = body["label"].strip(), body["message"].strip()
    if not body["label"] or not body["message"] or body["label"].startswith("__safety__"):
        raise Problem("VALIDATION_FAILED", "Enter a label and message; __safety__ is reserved.")
    kind = body["kind"]
    if (
        (kind == "restore") != bool(body["checkpoint_id"])
        or (kind == "schema") != (body["classes"] is not None)
        or (kind != "schema" and body["mapping"])
    ):
        raise Problem("VALIDATION_FAILED", "Provide only fields for the selected operation.")
    route = f"dataset-preview/{pid}"
    with srv.db.transaction() as conn:
        project = srv.maintain(conn, user, pid)
        replay = srv.replay(conn, user, route, key, body)
        if replay:
            return replay
        if row(
            conn, "SELECT id FROM dataset_checkpoints WHERE project_id=? AND label=?", (pid, body["label"])
        ):
            raise Problem("LABEL_EXISTS", "Choose a new checkpoint label.", 409)
        before = capture(srv, conn, project)
        target = (
            get_checkpoint(srv, user, pid, body["checkpoint_id"], conn)[1]
            if kind == "restore"
            else deepcopy(before)
        )
        schema_doc = srv.blobs.json(before["schema"]["blob_path"], before["schema"]["sha256"])
        if kind == "schema":
            reserved = rows(
                conn,
                "SELECT e.export_index FROM class_schema_entries e JOIN class_schemas s ON s.id=e.schema_id WHERE s.project_id=?",
                (pid,),
            )
            number = conn.exec_driver_sql(
                "SELECT max(number)+1 FROM class_schemas WHERE project_id=?", (pid,)
            ).scalar()
            schema_doc = edited_schema(schema_doc, body["classes"], pid, number, reserved)
        generation = project["dataset_generation"]
    before_content = checked_contents(srv, before)
    target_content = checked_contents(srv, target)
    if kind == "schema":
        target_content = {
            r["image_id"]: migrate_content(
                target_content[r["image_id"]], body["mapping"], schema_doc["entries"], r, project["task_type"]
            )
            for r in target["records"]
        }
        # Validate mapping even for an empty project.
        migrate_content(
            content_of(None),
            body["mapping"],
            schema_doc["entries"],
            {"width": 1, "height": 1},
            project["task_type"],
        )
        target["schema"] = {
            "id": schema_doc["id"],
            "project_id": pid,
            "number": schema_doc["number"],
            "blob_path": f"projects/{pid}/schemas/{schema_doc['id']}.json",
            "sha256": digest(canonical(schema_doc)),
        }
    ident = uid()
    payload = {
        "request": body,
        "before": before,
        "target": target,
        "schema_document": schema_doc if kind == "schema" else None,
        "target_content": target_content,
        "diff": semantic_diff(before, target, before_content, target_content),
    }
    path = f"projects/{pid}/dataset-operations/{ident}.json"
    data = canonical(payload)
    srv.blobs.publish(path, data)
    result = {
        "operation_id": ident,
        "kind": kind,
        "generation": generation,
        "label": body["label"],
        "message": body["message"],
        "images": len(target["records"]),
        "review_counts": target["review_counts"],
        "diff": payload["diff"],
        "requires_new_review": kind != "checkpoint",
        "source_sha256": digest(canonical(target)),
        "expires_at": after(86400),
    }
    with srv.db.transaction() as conn:
        project = srv.maintain(conn, user, pid)
        replay = srv.replay(conn, user, route, key, body)
        if replay:
            return replay
        if project["dataset_generation"] != generation:
            raise Problem("REVISION_CONFLICT", "Dataset changed while preparing; preview again.", 409)
        conn.exec_driver_sql(
            "INSERT INTO dataset_operations (id,project_id,created_by,kind,generation,blob_path,sha256,created_at,expires_at,result_json) VALUES (?,?,?,?,?,?,?,?,?,NULL)",
            (ident, pid, user["id"], kind, generation, path, digest(data), now(), result["expires_at"]),
        )
        srv.remember(conn, user, route, key, body, result)
        srv.audit(
            conn, user, "dataset.previewed", ident, pid, {"kind": kind, "generation": generation}, request_id
        )
    return result


def operation(srv, conn, user, pid, ident):
    srv.maintain(conn, user, pid)
    op = row(
        conn,
        "SELECT * FROM dataset_operations WHERE id=? AND project_id=? AND created_by=?",
        (ident, pid, user["id"]),
    )
    if not op:
        raise Problem("NOT_FOUND", "Dataset preview not found.", 404)
    if op["cancelled"]:
        raise Problem("OPERATION_CANCELLED", "Dataset preview was cancelled. Create a fresh preview.", 409)
    if not op["result_json"] and op["expires_at"] < now():
        raise Problem("PREVIEW_EXPIRED", "Create a fresh dataset preview.", 409)
    return op


def insert_checkpoint(srv, conn, user, pid, snapshot, label, message, restored=None):
    parent = row(
        conn,
        "SELECT id,sequence FROM dataset_checkpoints WHERE project_id=? ORDER BY sequence DESC LIMIT 1",
        (pid,),
    )
    if row(conn, "SELECT id FROM dataset_checkpoints WHERE project_id=? AND label=?", (pid, label)):
        raise Problem("LABEL_EXISTS", "Choose a new checkpoint label.", 409)
    ident = uid()
    data = canonical(snapshot)
    sha = digest(data)
    path = f"projects/{pid}/checkpoints/{sha}.json"
    srv.blobs.publish(path, data)
    conn.exec_driver_sql(
        "INSERT INTO dataset_checkpoints VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            ident,
            pid,
            parent["sequence"] + 1 if parent else 1,
            label,
            message,
            parent["id"] if parent else None,
            restored,
            path,
            sha,
            user["id"],
            now(),
        ),
    )
    return row(conn, "SELECT * FROM dataset_checkpoints WHERE id=?", (ident,))


def apply(srv, user, pid, ident, request_id, progress=None):
    with srv.db.engine.connect() as conn:
        op = operation(srv, conn, user, pid, ident)
        if op["result_json"]:
            return json.loads(op["result_json"])
        payload = srv.blobs.json(op["blob_path"], op["sha256"])
        all_heads = {
            r["image_id"]: r
            for r in rows(
                conn,
                "SELECT h.* FROM annotation_heads h JOIN images i ON i.id=h.image_id WHERE i.project_id=?",
                (pid,),
            )
        }
    before, target, request = payload["before"], payload["target"], payload["request"]
    checked_contents(srv, before, assets=True, progress=progress, phase="Verifying saved working data")
    if op["kind"] == "schema":
        schema = payload["schema_document"]
        srv.blobs.publish(target["schema"]["blob_path"], canonical(schema))
    else:
        checked_contents(srv, target, assets=True, progress=progress)
    staged = []
    timestamp = now()
    if op["kind"] != "checkpoint":
        for position, record in enumerate(target["records"]):
            if srv.stop.is_set():
                raise Problem(
                    "SERVER_STOPPING", "Dataset operation interrupted. Retry the saved preview.", 503
                )
            if progress:
                progress("Preparing immutable revisions", position, len(target["records"]))
            iid = record["image_id"]
            content = payload["target_content"][iid]
            revision = all_heads[iid]["current_revision"] + 1
            doc = content | {
                "schema_version": "1.0.0",
                "project_id": pid,
                "image_id": iid,
                "asset_sha256": record["asset_sha256"],
                "width": record["width"],
                "height": record["height"],
                "class_schema_id": target["schema"]["id"],
                "revision": revision,
                "created_by": user["id"],
                "created_at": timestamp,
            }
            data = canonical(doc)
            sha = digest(data)
            path = f"projects/{pid}/annotations/{iid}/r{revision:08d}-{sha}.json"
            srv.blobs.publish(path, data)
            staged.append((record, content, revision, path, sha))
    srv.fault("dataset_after_publish")
    if progress:
        progress("Committing dataset atomically", 0, 1, "transactions")
    with srv.db.transaction() as conn:
        op = operation(srv, conn, user, pid, ident)
        if op["result_json"]:
            return json.loads(op["result_json"])
        project = srv.maintain(conn, user, pid)
        safety = None
        if op["kind"] != "checkpoint":
            if project["dataset_generation"] != op["generation"]:
                raise Problem("REVISION_CONFLICT", "Dataset changed after preview. Preview again.", 409)
            if row(
                conn,
                "SELECT c.image_id FROM task_claims c JOIN images i ON i.id=c.image_id WHERE i.project_id=? AND c.expires_at>? LIMIT 1",
                (pid, now()),
            ):
                raise Problem(
                    "DATASET_CLAIMED",
                    "Release active image sessions before applying this dataset change.",
                    423,
                )
            safety = insert_checkpoint(
                srv, conn, user, pid, before, "__safety__" + ident, "Before " + request["label"]
            )
            if op["kind"] == "schema":
                schema = payload["schema_document"]
                conn.exec_driver_sql(
                    "INSERT INTO class_schemas VALUES (?,?,?,?,?,?,?)",
                    (
                        schema["id"],
                        pid,
                        schema["number"],
                        target["schema"]["blob_path"],
                        target["schema"]["sha256"],
                        timestamp,
                        user["id"],
                    ),
                )
                for entry in schema["entries"]:
                    conn.exec_driver_sql(
                        "INSERT OR IGNORE INTO classes VALUES (?,?,?)",
                        (entry["class_id"], pid, entry["stable_key"]),
                    )
                    conn.exec_driver_sql(
                        "INSERT INTO class_schema_entries VALUES (?,?,?,?,?,?)",
                        (
                            schema["id"],
                            entry["class_id"],
                            entry["display_name"],
                            entry["export_index"],
                            entry["color_hex"],
                            int(entry["active"]),
                        ),
                    )
            conn.exec_driver_sql(
                "UPDATE projects SET active_schema_id=?,project_revision=project_revision+1 WHERE id=?",
                (target["schema"]["id"], pid),
            )
            conn.exec_driver_sql("UPDATE images SET archived=1 WHERE project_id=? AND archived=0", (pid,))
            conn.exec_driver_sql(
                "UPDATE task_claims SET expires_at=?,generation=generation+1 WHERE image_id IN (SELECT id FROM images WHERE project_id=?)",
                (timestamp, pid),
            )
            # Fence even excluded heads; no revision is ever reset or deleted.
            conn.exec_driver_sql(
                "UPDATE annotation_heads SET state_revision=state_revision+1,updated_at=? WHERE image_id IN (SELECT id FROM images WHERE project_id=?)",
                (timestamp, pid),
            )
            for record, content, revision, path, sha in staged:
                iid = record["image_id"]
                srv.blobs.read(path, sha)
                conn.exec_driver_sql(
                    "UPDATE images SET archived=0,display_filename=?,group_key=?,created_at=? WHERE id=? AND project_id=?",
                    (record["display_filename"], record["group_key"], record["created_at"], iid, pid),
                )
                conn.exec_driver_sql(
                    "INSERT INTO annotation_revisions VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        iid,
                        revision,
                        target["schema"]["id"],
                        path,
                        sha,
                        int(content["verified_empty"]),
                        len(content["shapes"]),
                        timestamp,
                        user["id"],
                    ),
                )
                status = (
                    "IN_PROGRESS"
                    if content["shapes"] or content["image_labels"] or content["verified_empty"]
                    else "UNLABELED"
                )
                conn.exec_driver_sql(
                    "UPDATE annotation_heads SET current_revision=?,status=?,updated_at=? WHERE image_id=?",
                    (revision, status, timestamp, iid),
                )
                srv.audit(
                    conn,
                    user,
                    "annotation.dataset_restored"
                    if op["kind"] == "restore"
                    else "annotation.schema_migrated",
                    iid,
                    pid,
                    {
                        "operation_id": ident,
                        "revision": revision,
                        "source_revision": record["current_revision"],
                        "source_sha256": record["annotation_sha256"],
                        "source_checkpoint": request["checkpoint_id"],
                    },
                    request_id,
                )
            project = row(conn, "SELECT * FROM projects WHERE id=?", (pid,))
            target = capture(srv, conn, project)
        checkpoint = insert_checkpoint(
            srv, conn, user, pid, target, request["label"], request["message"], request["checkpoint_id"]
        )
        result = {"checkpoint": checkpoint, "safety_checkpoint": safety, "approved_release": False}
        conn.exec_driver_sql(
            "UPDATE dataset_operations SET result_json=? WHERE id=?", (canonical(result).decode(), ident)
        )
        srv.audit(
            conn,
            user,
            "dataset." + op["kind"],
            checkpoint["id"],
            pid,
            {
                "operation_id": ident,
                "sha256": checkpoint["sha256"],
                "safety_checkpoint_id": safety["id"] if safety else None,
            },
            request_id,
        )
        srv.fault("dataset_before_commit")
    srv.fault("dataset_after_commit")
    return result


def start_apply(srv, user, pid, ident, key, request_id):
    body = {"operation_id": ident}
    route = f"dataset-apply/{pid}"
    with srv.db.transaction() as conn:
        operation(srv, conn, user, pid, ident)
        replay = srv.replay(conn, user, route, key, body)
        if replay:
            return replay
        job_id = uid()
        conn.exec_driver_sql(
            "INSERT INTO jobs (id,project_id,created_by,type,state,payload_json,progress_total,created_at,updated_at) VALUES (?,?,?,'dataset-operation','queued',?,1,?,?)",
            (job_id, pid, user["id"], canonical(body).decode(), now(), now()),
        )
        result = {"job_id": job_id}
        srv.remember(conn, user, route, key, body, result, 202)

    def work():
        try:
            with srv.db.transaction() as conn:
                conn.exec_driver_sql(
                    "UPDATE jobs SET state='running',updated_at=? WHERE id=?", (now(), job_id)
                )
            from .export_progress import JobProgress

            progress = JobProgress(srv, job_id)
            result = apply(srv, user, pid, ident, request_id, progress)
            with srv.db.transaction() as conn:
                conn.exec_driver_sql(
                    "UPDATE jobs SET state='succeeded',progress_done=1,result_json=?,updated_at=? WHERE id=?",
                    (canonical(result).decode(), now(), job_id),
                )
        except Exception as exc:
            error = {
                "code": exc.code if isinstance(exc, Problem) else "DATASET_OPERATION_FAILED",
                "message": exc.message
                if isinstance(exc, Problem)
                else "Dataset operation failed. Retry the saved preview or create a fresh one.",
            }
            with srv.db.transaction() as conn:
                conn.exec_driver_sql(
                    "UPDATE jobs SET state='failed',error_json=?,updated_at=? WHERE id=?",
                    (canonical(error).decode(), now(), job_id),
                )

    srv.pool.submit(work)
    return result


def inspect(srv, user, pid, ident, offset=0, limit=100):
    checkpoint, snapshot = get_checkpoint(srv, user, pid, ident)
    schema = srv.blobs.json(snapshot["schema"]["blob_path"], snapshot["schema"]["sha256"])
    return {
        "checkpoint": checkpoint,
        "schema": schema,
        "review_counts": snapshot["review_counts"],
        "total": len(snapshot["records"]),
        "items": snapshot["records"][offset : offset + limit],
        "next_offset": offset + limit if offset + limit < len(snapshot["records"]) else None,
        "approved_release": False,
    }


def pending(srv, user, pid):
    with srv.db.engine.connect() as conn:
        srv.maintain(conn, user, pid)
        items = rows(
            conn,
            "SELECT * FROM dataset_operations WHERE project_id=? AND created_by=? AND result_json IS NULL AND cancelled=0 AND expires_at>? ORDER BY created_at DESC LIMIT 100",
            (pid, user["id"], now()),
        )
    result = []
    for item in items:
        data = srv.blobs.json(item["blob_path"], item["sha256"])
        result.append(
            {
                "operation_id": item["id"],
                "kind": item["kind"],
                "generation": item["generation"],
                "label": data["request"]["label"],
                "message": data["request"]["message"],
                "images": len(data["target"]["records"]),
                "review_counts": data["target"]["review_counts"],
                "diff": data["diff"],
                "requires_new_review": item["kind"] != "checkpoint",
                "expires_at": item["expires_at"],
            }
        )
    return {"items": result}


def cancel(srv, user, pid, ident, request_id):
    with srv.db.transaction() as conn:
        srv.maintain(conn, user, pid)
        op = row(
            conn,
            "SELECT * FROM dataset_operations WHERE id=? AND project_id=? AND created_by=?",
            (ident, pid, user["id"]),
        )
        if not op:
            raise Problem("NOT_FOUND", "Dataset preview not found.", 404)
        if op["result_json"]:
            return {"cancelled": False, "result": json.loads(op["result_json"])}
        if not op["cancelled"]:
            conn.exec_driver_sql("UPDATE dataset_operations SET cancelled=1 WHERE id=?", (ident,))
            srv.audit(conn, user, "dataset.cancelled", ident, pid, request_id=request_id)
        return {"cancelled": True}


def class_usage(srv, user, pid):
    with srv.db.engine.connect() as conn:
        conn.exec_driver_sql("BEGIN")
        source = capture(srv, conn, srv.authorize(conn, user, pid))
    contents = checked_contents(srv, source)
    schema = srv.blobs.json(source["schema"]["blob_path"], source["schema"]["sha256"])
    objects: Counter[str] = Counter()
    images: Counter[str] = Counter()
    for content in contents.values():
        labels = [s["class_id"] for s in content["shapes"]] + content["image_labels"]
        objects.update(labels)
        images.update(set(labels))
    return {
        "items": [
            {
                "class_id": e["class_id"],
                "name": e["display_name"],
                "objects": objects[e["class_id"]],
                "images": images[e["class_id"]],
            }
            for e in schema["entries"]
        ]
    }


def historical_image(srv, user, pid, ident, iid):
    checkpoint, snapshot = get_checkpoint(srv, user, pid, ident)
    record = next((r for r in snapshot["records"] if r["image_id"] == iid), None)
    if not record:
        raise Problem("NOT_FOUND", "Image is not in this checkpoint.", 404)
    doc = (
        srv.blobs.json(record["annotation_path"], record["annotation_sha256"])
        if record["current_revision"]
        else None
    )
    return {"image": record, "annotation": doc, "checkpoint_id": checkpoint["id"]}


def diff(srv, user, pid, ident, other=None):
    _, source = get_checkpoint(srv, user, pid, ident)
    if other:
        _, target = get_checkpoint(srv, user, pid, other)
    else:
        with srv.db.engine.connect() as conn:
            conn.exec_driver_sql("BEGIN")
            target = capture(srv, conn, srv.authorize(conn, user, pid))
    return semantic_diff(source, target, checked_contents(srv, source), checked_contents(srv, target))

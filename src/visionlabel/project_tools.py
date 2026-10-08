"""Service-owned project metadata and revision-bound annotation remapping."""

import copy
import json

from pydantic import Field, StrictBool

from .contracts import StrictModel
from .database import row, rows
from .domain import Problem, canonical, empty_content, uid


class ProjectUpdate(StrictModel):
    expected_project_revision: int = Field(ge=1, strict=True)
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    archived: StrictBool = False
    folder_id: str | None = None


class FolderUpdate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    parent_id: str | None = None
    expected_revision: int = Field(default=0, ge=0, strict=True)
    delete: StrictBool = False


class TemplateCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)


class RemapPreview(StrictModel):
    image_ids: list[str] = Field(min_length=1, max_length=500)
    mapping: dict[str, str] = Field(min_length=1, max_length=100)


class RemapApply(StrictModel):
    expected_revision: int = Field(ge=1, strict=True)
    expected_state_revision: int = Field(ge=0, strict=True)
    annotation_sha256: str = Field(min_length=64, max_length=64)
    class_schema_id: str
    mapping: dict[str, str] = Field(min_length=1, max_length=100)


def manage_folder(srv, conn, user, folder_id):
    folder = row(conn, "SELECT * FROM project_folders WHERE id=?", (folder_id,))
    principal = srv.principal(conn, user)
    if not folder or (folder["owner_id"] != user["id"] and not principal["is_admin"]):
        raise Problem("NOT_FOUND", "Folder not found or not managed by this account.", 404)
    return folder


def update_project(srv, user, pid, body, key, request_id):
    with srv.db.transaction() as conn:
        project = srv.maintain(conn, user, pid, allow_archived=True)
        replay = srv.replay(conn, user, f"project-meta/{pid}", key, body)
        if replay:
            return replay
        if project["project_revision"] != body["expected_project_revision"]:
            raise Problem("REVISION_CONFLICT", "Project changed. Refresh before saving.", 409)
        if not body["name"].strip():
            raise Problem("VALIDATION_FAILED", "Project name cannot be blank.")
        if body["folder_id"]:
            manage_folder(srv, conn, user, body["folder_id"])
        conn.exec_driver_sql(
            "UPDATE projects SET name=?,description=?,archived=?,folder_id=?,project_revision=project_revision+1 WHERE id=?",
            (body["name"].strip(), body["description"], int(body["archived"]), body["folder_id"], pid),
        )
        result = row(conn, "SELECT * FROM projects WHERE id=?", (pid,))
        srv.audit(conn, user, "project.updated", pid, pid, body, request_id)
        srv.remember(conn, user, f"project-meta/{pid}", key, body, result)
        return result


def update_folder(srv, user, fid, body, key, request_id):
    from .service import now

    scope = f"folder/{fid or 'new'}"
    with srv.db.transaction() as conn:
        principal = srv.principal(conn, user)
        if not principal["is_admin"] and not row(
            conn, "SELECT 1 FROM project_members WHERE user_id=? AND role='maintainer'", (user["id"],)
        ):
            raise Problem("FORBIDDEN", "Maintainer permission is required.", 403)
        replay = srv.replay(conn, user, scope, key, body)
        if replay:
            return replay
        if fid:
            existing = manage_folder(srv, conn, user, fid)
        if fid and existing["revision"] != body["expected_revision"]:
            raise Problem("REVISION_CONFLICT", "Folder changed. Refresh first.", 409)
        if not body["name"].strip():
            raise Problem("VALIDATION_FAILED", "Folder name cannot be blank.")
        parent = body["parent_id"]
        seen = {fid}
        while parent:
            if parent in seen:
                raise Problem("FOLDER_CYCLE", "A folder cannot contain itself.")
            seen.add(parent)
            parent = manage_folder(srv, conn, user, parent)["parent_id"]
        if body["delete"]:
            if not fid or row(
                conn,
                "SELECT 1 FROM project_folders WHERE parent_id=? UNION ALL SELECT 1 FROM projects WHERE folder_id=?",
                (fid, fid),
            ):
                raise Problem("FOLDER_NOT_EMPTY", "Only an empty folder can be deleted.", 409)
            conn.exec_driver_sql("DELETE FROM project_folders WHERE id=?", (fid,))
            result = {"id": fid, "deleted": True}
        elif fid:
            conn.exec_driver_sql(
                "UPDATE project_folders SET name=?,parent_id=?,revision=revision+1 WHERE id=?",
                (body["name"].strip(), body["parent_id"], fid),
            )
            result = row(conn, "SELECT * FROM project_folders WHERE id=?", (fid,))
        else:
            fid = uid()
            conn.exec_driver_sql(
                "INSERT INTO project_folders VALUES (?,?,?,?,1)",
                (fid, body["name"].strip(), body["parent_id"], user["id"]),
            )
            result = row(conn, "SELECT * FROM project_folders WHERE id=?", (fid,))
        srv.audit(conn, user, "folder.updated", fid, detail=body | {"at": now()}, request_id=request_id)
        srv.remember(conn, user, scope, key, body, result)
        return result


def list_folders(srv, user):
    with srv.db.engine.connect() as conn:
        principal = srv.principal(conn, user)
        all_folders = {f["id"]: f for f in rows(conn, "SELECT * FROM project_folders ORDER BY name,id")}
        visible = {
            f["id"] for f in all_folders.values() if principal["is_admin"] or f["owner_id"] == user["id"]
        }
        visible.update(
            p["folder_id"]
            for p in rows(
                conn,
                "SELECT p.folder_id FROM projects p JOIN project_members m ON m.project_id=p.id WHERE m.user_id=?",
                (user["id"],),
            )
            if p["folder_id"]
        )
        for fid in list(visible):
            while fid and fid in all_folders:
                visible.add(fid)
                fid = all_folders[fid]["parent_id"]
        return {"items": [f for fid, f in all_folders.items() if fid in visible]}


def template(srv, user, pid, body, key, request_id):
    from .service import now

    with srv.db.transaction() as conn:
        project = srv.maintain(conn, user, pid)
        replay = srv.replay(conn, user, f"template/{pid}", key, body)
        if replay:
            return replay
        names = [
            r["display_name"]
            for r in rows(
                conn,
                "SELECT display_name FROM class_schema_entries WHERE schema_id=? AND active=1 ORDER BY export_index",
                (project["active_schema_id"],),
            )
        ]
        result = {
            "id": uid(),
            "name": body["name"],
            "task_type": project["task_type"],
            "initial_classes": names,
        }
        conn.exec_driver_sql(
            "INSERT INTO class_templates VALUES (?,?,?,?,?,?)",
            (result["id"], user["id"], body["name"], project["task_type"], canonical(names).decode(), now()),
        )
        srv.audit(
            conn,
            user,
            "template.created",
            result["id"],
            pid,
            {"schema_id": project["active_schema_id"]},
            request_id,
        )
        srv.remember(conn, user, f"template/{pid}", key, body, result)
        return result


def remap_content(content, mapping, entries):
    known = {e["class_id"] for e in entries}
    active = {e["class_id"] for e in entries if e["active"]}
    if not mapping.keys() <= known or not set(mapping.values()) <= active:
        raise Problem(
            "INVALID_MAPPING", "Remapping requires existing source classes and active destination classes."
        )
    result = copy.deepcopy(content)
    count = 0
    for shape in result["shapes"]:
        target = mapping.get(shape["class_id"], shape["class_id"])
        count += target != shape["class_id"]
        shape["class_id"] = target
    labels = [mapping.get(c, c) for c in result["image_labels"]]
    count += labels != result["image_labels"]
    result["image_labels"] = labels
    return result, count


def preview_remap(srv, user, pid, body):
    project = srv.project(user, pid)
    with srv.db.engine.connect() as conn:
        srv.maintain(conn, user, pid)
    remap_content(empty_content(), body["mapping"], project["schema"]["entries"])
    items = []
    for image_id in dict.fromkeys(body["image_ids"]):
        with srv.db.engine.connect() as conn:
            image = srv.image(conn, user, image_id)
        if image["project_id"] != pid:
            raise Problem("WRONG_PROJECT", "Selected image belongs to another project.")
        head = srv.annotation(user, image_id)
        if not head["annotation"]:
            continue
        content = {k: head["annotation"][k] for k in ("shapes", "image_labels", "verified_empty")}
        after, count = remap_content(content, body["mapping"], project["schema"]["entries"])
        items.append(
            {
                "image_id": image_id,
                "filename": image["display_filename"],
                "changed_labels": count,
                "expected_revision": head["revision"],
                "expected_state_revision": head["state_revision"],
                "annotation_sha256": head["annotation_sha256"],
                "class_schema_id": project["active_schema_id"],
                "before": content,
                "after": after,
            }
        )
    return {
        "project_id": pid,
        "mapping": body["mapping"],
        "items": items,
        "changed_images": sum(i["changed_labels"] > 0 for i in items),
    }


def apply_remap(srv, user, image_id, body, headers, key, request_id):
    with srv.db.engine.connect() as conn:
        image = srv.image(conn, user, image_id, True)
        project = srv.maintain(conn, user, image["project_id"])
        entries = rows(
            conn, "SELECT * FROM class_schema_entries WHERE schema_id=?", (body["class_schema_id"],)
        )
        if project["active_schema_id"] != body["class_schema_id"]:
            raise Problem("SCHEMA_CHANGED", "Refresh the remap preview.", 409)
        revision = row(
            conn,
            "SELECT * FROM annotation_revisions WHERE image_id=? AND revision=?",
            (image_id, body["expected_revision"]),
        )
    if not revision or revision["sha256"] != body["annotation_sha256"]:
        raise Problem("REVISION_CONFLICT", "Remap source does not match the preview.", 409)
    doc = srv.blobs.json(revision["blob_path"], revision["sha256"])
    content, count = remap_content(
        {k: doc[k] for k in ("shapes", "image_labels", "verified_empty")}, body["mapping"], entries
    )
    if not count:
        raise Problem("NO_CHANGES", "This mapping does not change the selected annotation.")
    save = {k: body[k] for k in ("expected_revision", "expected_state_revision", "class_schema_id")}
    return srv.save(
        user,
        image_id,
        save | {"content": content},
        headers,
        key,
        request_id,
        remap_provenance={"mapping": body["mapping"], "source_sha256": body["annotation_sha256"]},
    )


def versions(srv, user, pid):
    with srv.db.engine.connect() as conn:
        project = srv.authorize(conn, user, pid)
        schemas = rows(
            conn,
            "SELECT id,number,sha256,created_at FROM class_schemas WHERE project_id=? ORDER BY number",
            (pid,),
        )
        heads = rows(
            conn,
            "SELECT i.id,h.current_revision,h.updated_at FROM images i JOIN annotation_heads h ON h.image_id=i.id WHERE i.project_id=? AND i.archived=0 ORDER BY i.id",
            (pid,),
        )
        exports = rows(
            conn,
            "SELECT id,state,created_at,payload_json,result_json,error_json FROM jobs WHERE project_id=? AND type='working-export' ORDER BY created_at DESC,id DESC",
            (pid,),
        )
    for job in exports:
        payload = json.loads(job.pop("payload_json"))
        from .domain import digest

        job["snapshot_sha256"] = digest(canonical(payload))
        job["schema_id"] = payload["schema"]["id"]
        job["options"] = payload["options"]
        job["format_version"] = payload.get("format_version", "vl-formats-1")
        job["approved_release"] = False
        job["result"] = json.loads(job.pop("result_json") or "null")
        job["error"] = json.loads(job.pop("error_json") or "null")
    return {
        "working": {
            "project_revision": project["project_revision"],
            "images": len(heads),
            "last_modified": max((h["updated_at"] for h in heads), default=None),
        },
        "schemas": schemas,
        "exports": exports,
        "approved_releases": [],
        "release_status": "Reviewed releases are not implemented.",
    }

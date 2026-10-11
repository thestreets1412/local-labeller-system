"""Working-review policy and service transactions; no released approvals."""

from typing import Literal

from pydantic import Field, StrictBool

from .contracts import StrictModel
from .database import row, rows
from .domain import Problem, uid, validate_content

STATES = ("UNLABELED", "IN_PROGRESS", "REVIEWED_PASS", "REVIEWED_NG")
EDITABLE = (*STATES, "ANNOTATED", "REJECTED")


class ReviewRequest(StrictModel):
    expected_revision: int = Field(ge=1, strict=True)
    expected_state_revision: int = Field(ge=0, strict=True)
    annotation_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    decision: Literal["accept", "reject"]
    comment: str = Field(default="", max_length=2000)


class ReviewSettings(StrictModel):
    expected_project_revision: int = Field(ge=1, strict=True)
    allow_self_review: StrictBool
    reason: str = Field(min_length=1, max_length=2000)


def require_role(srv, conn, user, pid, roles):
    project = srv.authorize(conn, user, pid)
    member = row(conn, "SELECT role FROM project_members WHERE project_id=? AND user_id=?", (pid, user["id"]))
    if not member or member["role"] not in roles:
        raise Problem("FORBIDDEN", "An appropriate project role is required.", 403)
    if project["archived"]:
        raise Problem("PROJECT_ARCHIVED", "Restore this project before making changes.", 409)
    return project


def settings(srv, user, pid, body, key, request_id):
    with srv.db.transaction() as conn:
        project = srv.maintain(conn, user, pid)
        replay = srv.replay(conn, user, f"review-settings/{pid}", key, body)
        if replay:
            return replay
        if not body["reason"].strip():
            raise Problem("VALIDATION_FAILED", "A reason is required.")
        if project["project_revision"] != body["expected_project_revision"]:
            raise Problem("REVISION_CONFLICT", "Refresh the project settings.", 409)
        conn.exec_driver_sql(
            "UPDATE projects SET allow_self_review=?,project_revision=project_revision+1 WHERE id=?",
            (int(body["allow_self_review"]), pid),
        )
        result = {
            "allow_self_review": body["allow_self_review"],
            "project_revision": project["project_revision"] + 1,
        }
        srv.audit(conn, user, "review.settings_changed", pid, pid, body, request_id)
        srv.remember(conn, user, f"review-settings/{pid}", key, body, result)
        return result


def decide(srv, user, iid, body, headers, key, request_id):
    from .service import now

    with srv.db.transaction() as conn:
        image = srv.image(conn, user, iid)
        project = require_role(srv, conn, user, image["project_id"], ("reviewer", "maintainer"))
        replay = srv.replay(conn, user, f"review/{iid}", key, body)
        if replay:
            return replay
        claim = srv.check_claim(conn, user, iid, headers)
        if claim["mode"] != "review":
            raise Problem("STATE_CONFLICT", "Acquire a review lease first.", 409)
        if (
            image["status"] != "IN_PROGRESS"
            or image["current_revision"] != body["expected_revision"]
            or image["state_revision"] != body["expected_state_revision"]
        ):
            raise Problem("REVISION_CONFLICT", "The review target changed. Reload before reviewing.", 409)
        revision = row(
            conn,
            "SELECT * FROM annotation_revisions WHERE image_id=? AND revision=?",
            (iid, image["current_revision"]),
        )
        if (
            not revision
            or revision["sha256"] != body["annotation_sha256"]
            or revision["schema_id"] != project["active_schema_id"]
        ):
            raise Problem("REVISION_CONFLICT", "The annotation hash or schema changed.", 409)
        if revision["created_by"] == user["id"] and not project["allow_self_review"]:
            raise Problem(
                "SELF_REVIEW_DISABLED",
                "Self-review is disabled. Ask another reviewer or enable the audited solo-project setting.",
                403,
            )
        if body["decision"] == "reject" and not body["comment"].strip():
            raise Problem("VALIDATION_FAILED", "A rejection reason is required.")
        doc = srv.blobs.json(revision["blob_path"], revision["sha256"])
        if body["decision"] == "accept":
            classes = [
                r["class_id"]
                for r in rows(
                    conn,
                    "SELECT class_id FROM class_schema_entries WHERE schema_id=? AND active=1",
                    (revision["schema_id"],),
                )
            ]
            content = validate_content(
                {k: doc[k] for k in ("shapes", "image_labels", "verified_empty")},
                image["width"],
                image["height"],
                project["task_type"],
                classes,
            )
            if not (
                content["image_labels"]
                if project["task_type"] == "classification"
                else content["shapes"] or content["verified_empty"]
            ):
                raise Problem(
                    "INCOMPLETE_ANNOTATION",
                    "Label the image or explicitly verify an empty image before accepting.",
                )
        ident, stamp = uid(), now()
        state = "REVIEWED_PASS" if body["decision"] == "accept" else "REVIEWED_NG"
        conn.exec_driver_sql(
            "INSERT INTO working_reviews VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                ident,
                iid,
                revision["revision"],
                revision["sha256"],
                revision["schema_id"],
                image["state_revision"] + 1,
                body["decision"],
                body["comment"].strip(),
                user["id"],
                stamp,
            ),
        )
        conn.exec_driver_sql(
            "UPDATE annotation_heads SET state_revision=state_revision+1,status=?,updated_at=? WHERE image_id=?",
            (state, stamp, iid),
        )
        conn.exec_driver_sql(
            "UPDATE task_claims SET expires_at=?,generation=generation+1 WHERE image_id=?", (stamp, iid)
        )
        result = {
            "review_id": ident,
            "status": state,
            "revision": revision["revision"],
            "state_revision": image["state_revision"] + 1,
            "annotation_sha256": revision["sha256"],
            "comment": body["comment"].strip(),
        }
        srv.audit(conn, user, "annotation.reviewed", iid, image["project_id"], result, request_id)
        srv.remember(conn, user, f"review/{iid}", key, body, result, 201)
        return result


def overview(srv, user, pid):
    with srv.db.engine.connect() as conn:
        conn.exec_driver_sql("BEGIN")
        srv.authorize(conn, user, pid)
        images = rows(
            conn,
            "SELECT i.id,h.status FROM images i JOIN annotation_heads h ON h.image_id=i.id WHERE i.project_id=? AND i.archived=0 ORDER BY i.created_at,i.id",
            (pid,),
        )
    counts = dict.fromkeys(STATES, 0)
    for image in images:
        counts[image["status"]] = counts.get(image["status"], 0) + 1
    return {"total": len(images), "image_ids": [i["id"] for i in images], "counts": counts}


def history(srv, user, iid):
    with srv.db.engine.connect() as conn:
        conn.exec_driver_sql("BEGIN")
        image = srv.image(conn, user, iid)
        decisions = rows(
            conn,
            "SELECT r.*,u.display_name AS reviewer_name FROM working_reviews r JOIN users u ON u.id=r.reviewer_id WHERE r.image_id=? ORDER BY r.state_revision DESC",
            (iid,),
        )
        for decision in decisions:
            decision["applicable"] = (
                decision["state_revision"] == image["state_revision"]
                and decision["annotation_revision"] == image["current_revision"]
                and image["status"] in ("REVIEWED_PASS", "REVIEWED_NG")
            )
    return {"items": decisions}

import io
import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest
from conftest import claim, import_files, project, save_body
from test_team import create_user, member
from test_working_export import labeled, wait

from visionlabel.database import rows
from visionlabel.domain import uid


def mutation(client, method, path, body, lease=None, key=None):
    return client.request(
        method, "/api/v1" + path, json=body, headers=(lease or {}) | {"Idempotency-Key": key or uid()}
    )


def enable_solo(client, proj):
    current = client.get(f"/api/v1/projects/{proj['id']}").json()
    response = mutation(
        client,
        "PUT",
        f"/projects/{proj['id']}/review-settings",
        {
            "expected_project_revision": current["project_revision"],
            "allow_self_review": True,
            "reason": "Single operator validation",
        },
    )
    assert response.status_code == 200, response.text


def review_claim(client, iid):
    response = mutation(
        client, "POST", f"/images/{iid}/claim", {"mode": "review", "client_instance_id": uid()}
    )
    assert response.status_code == 201, response.text
    result = response.json()
    return {
        "X-Claim-ID": result["claim_id"],
        "X-Claim-Token": result["claim_token"],
        "X-Claim-Generation": str(result["generation"]),
    }


def decision_body(client, iid, decision="accept"):
    head = client.get(f"/api/v1/images/{iid}/annotation").json()
    return {
        "expected_revision": head["revision"],
        "expected_state_revision": head["state_revision"],
        "annotation_sha256": head["annotation_sha256"],
        "decision": decision,
        "comment": "Wrong class" if decision == "reject" else "",
    }


@pytest.mark.parametrize("task", ["detection", "segmentation", "classification"])
@pytest.mark.parametrize("decision,state", [("accept", "REVIEWED_PASS"), ("reject", "REVIEWED_NG")])
def test_review_edit_invalidates_and_noop_preserves_history(environment, task, decision, state):
    client, srv, root = environment
    proj, images = labeled(client, root, task, 1)
    iid = images[0]["id"]
    enable_solo(client, proj)
    lease = review_claim(client, iid)
    body = decision_body(client, iid, decision)
    key = uid()
    result = mutation(client, "POST", f"/images/{iid}/reviews", body, lease, key)
    assert result.status_code == 201, result.text
    assert result.json()["status"] == state
    assert mutation(client, "POST", f"/images/{iid}/reviews", body, lease, key).json() == result.json()
    head = client.get(f"/api/v1/images/{iid}/annotation").json()
    assert (head["revision"], head["state_revision"]) == (1, 2)
    edit_lease = claim(client, iid)
    content = {k: head["annotation"][k] for k in ("shapes", "image_labels", "verified_empty")}
    save = {
        "expected_revision": 1,
        "expected_state_revision": 2,
        "class_schema_id": proj["active_schema_id"],
        "content": content,
    }
    noop = mutation(client, "PUT", f"/images/{iid}/annotation", save, edit_lease)
    assert noop.status_code == 200 and noop.json()["status"] == state
    assert noop.json()["revision"] == 1
    if task == "classification":
        content["image_labels"] = [proj["schema"]["entries"][1]["class_id"]]
    else:
        content["shapes"][0]["class_id"] = proj["schema"]["entries"][1]["class_id"]
    corrected = mutation(client, "PUT", f"/images/{iid}/annotation", save, edit_lease)
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["status"] == "IN_PROGRESS"
    history = client.get(f"/api/v1/images/{iid}/reviews").json()["items"]
    assert len(history) == 1 and not history[0]["applicable"]
    assert history[0]["annotation_sha256"] == body["annotation_sha256"]
    client.delete(f"/api/v1/images/{iid}/claim", headers=edit_lease)
    reviewed = mutation(
        client, "POST", f"/images/{iid}/reviews", decision_body(client, iid), review_claim(client, iid)
    )
    assert reviewed.status_code == 201
    with srv.db.engine.connect() as conn:
        assert len(rows(conn, "SELECT * FROM working_reviews WHERE image_id=?", (iid,))) == 2


def test_review_roles_default_self_review_and_wrong_claim(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=1)
    iid = images[0]["id"]
    admin_header = client.headers["Authorization"]
    body = decision_body(client, iid)
    lease = review_claim(client, iid)
    denied = mutation(client, "POST", f"/images/{iid}/reviews", body, lease)
    assert denied.status_code == 403 and denied.json()["error"]["code"] == "SELF_REVIEW_DISABLED"
    client.delete(f"/api/v1/images/{iid}/claim", headers=lease)
    reviewer = create_user(client)
    assert member(client, proj, reviewer, "reviewer").status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    capabilities = client.get(f"/api/v1/projects/{proj['id']}").json()
    assert not capabilities["can_edit"] and capabilities["can_review"]
    assert (
        mutation(
            client, "POST", f"/images/{iid}/claim", {"mode": "edit", "client_instance_id": uid()}
        ).status_code
        == 403
    )
    assert (
        mutation(client, "PUT", f"/images/{iid}/annotation", save_body(proj, 1, 1), lease).status_code == 403
    )
    lease = review_claim(client, iid)
    assert client.post(f"/api/v1/images/{iid}/claim/heartbeat", headers=lease).status_code == 200
    result = mutation(client, "POST", f"/images/{iid}/reviews", body, lease)
    assert result.status_code == 201, result.text
    client.headers["Authorization"] = admin_header
    assert member(client, proj, reviewer, "annotator", 2).status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    assert mutation(client, "POST", f"/images/{iid}/reviews", body, lease).status_code == 403
    edit = claim(client, iid)
    assert (
        mutation(client, "PUT", f"/images/{iid}/annotation", save_body(proj, 1, 2), edit).status_code == 200
    )


def test_stale_review_claim_revocation_and_revision_race(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=1)
    iid = images[0]["id"]
    enable_solo(client, proj)
    old = decision_body(client, iid)
    lease = review_claim(client, iid)
    # A review lease excludes even the same user's editing session.
    assert (
        mutation(
            client, "POST", f"/images/{iid}/claim", {"mode": "edit", "client_instance_id": uid()}
        ).status_code
        == 423
    )
    assert (
        mutation(client, "PUT", f"/images/{iid}/annotation", save_body(proj, 1, 1), lease).status_code == 409
    )
    client.delete(f"/api/v1/images/{iid}/claim", headers=lease)
    edit = claim(client, iid)
    assert (
        mutation(client, "PUT", f"/images/{iid}/annotation", save_body(proj, 1, 1), edit).status_code == 200
    )
    assert mutation(client, "POST", f"/images/{iid}/reviews", old, lease).status_code == 409
    client.delete(f"/api/v1/images/{iid}/claim", headers=edit)
    current = review_claim(client, iid)
    assert mutation(client, "POST", f"/images/{iid}/reviews", old, current).status_code == 409
    body = decision_body(client, iid)
    # Two independent requests with the same captured revision: one decision wins.
    barrier = threading.Barrier(2)

    def send():
        barrier.wait()
        return mutation(client, "POST", f"/images/{iid}/reviews", body, current).status_code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: send(), range(2)))
    assert sorted(results) == [201, 409]


def test_reject_reason_and_empty_accept(environment):
    client, _, root = environment
    proj = project(client)
    iid = import_files(client, root, proj["id"])[0]["id"]
    enable_solo(client, proj)
    assert (
        mutation(
            client, "POST", f"/images/{iid}/claim", {"mode": "review", "client_instance_id": uid()}
        ).status_code
        == 409
    )
    lease = claim(client, iid)
    body = save_body(proj)
    body["content"]["shapes"] = []
    assert mutation(client, "PUT", f"/images/{iid}/annotation", body, lease).status_code == 200
    client.delete(f"/api/v1/images/{iid}/claim", headers=lease)
    lease = review_claim(client, iid)
    assert (
        mutation(client, "POST", f"/images/{iid}/reviews", decision_body(client, iid), lease).status_code
        == 422
    )
    reject = decision_body(client, iid, "reject") | {"comment": "   "}
    assert mutation(client, "POST", f"/images/{iid}/reviews", reject, lease).status_code == 422
    assert (
        mutation(
            client, "POST", f"/images/{iid}/reviews", reject | {"comment": "Missing objects"}, lease
        ).status_code
        == 201
    )


def test_export_confirmation_freezes_revision_counts_options_and_actor(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=3)
    path = f"/projects/{proj['id']}/working-exports"
    options = {"test_percent": 0}
    response = mutation(client, "POST", path, options)
    assert response.status_code == 409
    detail = response.json()["error"]["details"]
    assert detail["counts"] == {"IN_PROGRESS": 3}
    with srv.db.engine.connect() as conn:
        assert not rows(conn, "SELECT id FROM jobs WHERE type='working-export'")
    assert mutation(client, "POST", path, options | {"confirmation": uid()}).status_code == 409
    assert (
        mutation(
            client, "POST", path, {"confirmation": detail["confirmation"], "test_percent": 1}
        ).status_code
        == 409
    )
    iid = images[0]["id"]
    lease = claim(client, iid)
    assert (
        mutation(client, "PUT", f"/images/{iid}/annotation", save_body(proj, 1, 1), lease).status_code == 200
    )
    confirmed = options | {"confirmation": detail["confirmation"]}
    key = uid()
    export = mutation(client, "POST", path, confirmed, key=key)
    assert export.status_code == 202, export.text
    assert mutation(client, "POST", path, confirmed, key=key).json() == export.json()
    job = wait(client, export.json()["job_id"])
    assert job["state"] == "succeeded", job
    bundle = zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/working-exports/{job['id']}/download").content))
    manifest = json.loads(bundle.read("manifest.json"))
    assert manifest["snapshot_sha256"] == detail["snapshot_sha256"]
    assert not manifest["approved_release"] and manifest["review_counts"] == {"IN_PROGRESS": 3}
    assert all(r["current_revision"] == 1 for r in manifest["review_evidence"])


def test_all_pass_export_needs_no_confirmation_and_overview_unfiltered(environment):
    client, _, root = environment
    proj, images = labeled(client, root, count=3)
    enable_solo(client, proj)
    for image in images:
        iid = image["id"]
        assert (
            mutation(
                client,
                "POST",
                f"/images/{iid}/reviews",
                decision_body(client, iid),
                review_claim(client, iid),
            ).status_code
            == 201
        )
    overview = client.get(f"/api/v1/projects/{proj['id']}/review-overview").json()
    assert overview["total"] == 3 and overview["counts"]["REVIEWED_PASS"] == 3
    assert overview["image_ids"] == [i["id"] for i in images]
    assert client.get(f"/api/v1/projects/{proj['id']}/images?status=IN_PROGRESS").json()["items"] == []
    result = mutation(client, "POST", f"/projects/{proj['id']}/working-exports", {"test_percent": 0})
    assert result.status_code == 202, result.text


def test_role_revocation_blocks_review_and_admin_needs_project_role(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=1)
    iid = images[0]["id"]
    admin_auth = client.headers["Authorization"]
    admin = client.get("/api/v1/me").json()
    other = create_user(client)
    assert member(client, proj, other, "reviewer").status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    lease = review_claim(client, iid)
    body = decision_body(client, iid)
    client.headers["Authorization"] = admin_auth
    assert member(client, proj, other, "viewer", 2).status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    assert mutation(client, "POST", f"/images/{iid}/reviews", body, lease).status_code == 403
    client.headers["Authorization"] = admin_auth
    assert member(client, proj, other, "maintainer", 3).status_code == 200
    assert member(client, proj, admin, "viewer", 4).status_code == 200
    assert (
        mutation(
            client, "POST", f"/images/{iid}/claim", {"mode": "edit", "client_instance_id": uid()}
        ).status_code
        == 403
    )
    assert (
        mutation(
            client, "POST", f"/images/{iid}/claim", {"mode": "review", "client_instance_id": uid()}
        ).status_code
        == 403
    )
    assert mutation(client, "POST", f"/projects/{proj['id']}/working-exports", {}).status_code == 403


def test_verified_empty_review_and_backup_restore_evidence(environment, tmp_path):
    from visionlabel.operations import backup, restore
    from visionlabel.review import history
    from visionlabel.service import Service

    client, srv, root = environment
    proj = project(client)
    iid = import_files(client, root, proj["id"])[0]["id"]
    body = save_body(proj)
    body["content"] = {"verified_empty": True, "shapes": [], "image_labels": []}
    edit = claim(client, iid)
    assert mutation(client, "PUT", f"/images/{iid}/annotation", body, edit).status_code == 200
    client.delete(f"/api/v1/images/{iid}/claim", headers=edit)
    enable_solo(client, proj)
    result = mutation(
        client, "POST", f"/images/{iid}/reviews", decision_body(client, iid), review_claim(client, iid)
    )
    assert result.status_code == 201
    original = client.get(f"/api/v1/images/{iid}/reviews").json()
    srv.close()
    backup(root, tmp_path / "review-backup")
    restore(tmp_path / "review-backup", tmp_path / "review-restored")
    restored = Service(tmp_path / "review-restored")
    try:
        user = restored.authenticate(restored.login("admin", "a-strong-test-password")["token"])
        assert history(restored, user, iid) == original
        assert restored.annotation(user, iid)["status"] == "REVIEWED_PASS"
    finally:
        restored.close()


def test_remapping_a_reviewed_revision_invalidates_decision(environment):
    client, _, root = environment
    proj, images = labeled(client, root, count=1)
    iid = images[0]["id"]
    enable_solo(client, proj)
    original = decision_body(client, iid)
    assert (
        mutation(client, "POST", f"/images/{iid}/reviews", original, review_claim(client, iid)).status_code
        == 201
    )
    classes = proj["schema"]["entries"]
    mapping = {classes[0]["class_id"]: classes[1]["class_id"]}
    preview = mutation(
        client, "POST", f"/projects/{proj['id']}/remap-preview", {"image_ids": [iid], "mapping": mapping}
    )
    assert preview.status_code == 200
    body = {
        "expected_revision": 1,
        "expected_state_revision": 2,
        "annotation_sha256": original["annotation_sha256"],
        "class_schema_id": proj["active_schema_id"],
        "mapping": mapping,
    }
    result = mutation(client, "POST", f"/images/{iid}/remap", body, claim(client, iid))
    assert result.status_code == 200, result.text
    assert result.json()["status"] == "IN_PROGRESS"
    assert not client.get(f"/api/v1/images/{iid}/reviews").json()["items"][0]["applicable"]

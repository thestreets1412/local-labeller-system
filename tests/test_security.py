import copy

import pytest
from conftest import claim, import_files, project, save_body

from visionlabel.domain import Problem, uid
from visionlabel.service import now, password_hash
from visionlabel.storage import local_directory


def test_cross_project_and_viewer_permissions(environment):
    client, service, root = environment
    first, second = project(client), project(client)
    image = import_files(client, root, first["id"])[0]
    second_image = import_files(client, root, second["id"])[0]
    user_id = uid()
    with service.db.transaction() as conn:
        conn.exec_driver_sql(
            "INSERT INTO users (id,username,display_name,password_hash,is_admin,created_at) VALUES (?,?,?,?,0,?)",
            (user_id, "viewer", "Viewer", password_hash("viewer-test-password"), now()),
        )
        conn.exec_driver_sql("INSERT INTO project_members VALUES (?,?,'viewer')", (first["id"], user_id))
    token = service.login("viewer", "viewer-test-password")["token"]
    client.headers["Authorization"] = "Bearer " + token
    assert client.get(f"/api/v1/images/{image['id']}/content").status_code == 200
    assert client.get(f"/api/v1/images/{second_image['id']}/content").status_code == 404
    assert (
        client.post(
            f"/api/v1/images/{image['id']}/claim",
            json={"mode": "edit", "client_instance_id": uid()},
            headers={"Idempotency-Key": uid()},
        ).status_code
        == 403
    )
    assert "_token_hash" not in client.get("/api/v1/me").json()


def test_revoked_token_between_publish_and_commit(environment):
    client, service, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    lease = claim(client, image["id"])

    def revoke(point):
        if point == "after_publish":
            with service.db.transaction() as conn:
                conn.exec_driver_sql("UPDATE auth_tokens SET revoked_at=?", (now(),))

    service.fault = revoke
    response = client.put(
        f"/api/v1/images/{image['id']}/annotation",
        json=save_body(proj),
        headers=dict(lease, **{"Idempotency-Key": uid()}),
    )
    assert response.status_code == 401, response.text
    with service.db.engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT current_revision FROM annotation_heads").scalar() == 0


@pytest.mark.parametrize(
    "changes", [{"x1": float("nan")}, {"class_id": []}, {"id": "not-uuid"}, {"x2": 500}, {"extra": True}]
)
def test_invalid_shape_reports_validation(environment, changes):
    client, service, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    lease = claim(client, image["id"])
    body = copy.deepcopy(save_body(proj))
    body["content"]["shapes"][0].update(changes)
    import json

    response = client.put(
        f"/api/v1/images/{image['id']}/annotation",
        content=json.dumps(body),
        headers=dict(lease, **{"Idempotency-Key": uid(), "Content-Type": "application/json"}),
    )
    assert response.status_code == 422, response.text


def test_unc_and_mapped_drive_rejected(tmp_path, monkeypatch):
    from pathlib import Path

    import visionlabel.storage as storage

    with pytest.raises(Problem):
        local_directory(Path(r"\\server\share\db"))
    monkeypatch.setattr(storage.ctypes.windll.kernel32, "GetDriveTypeW", lambda _: 4)
    with pytest.raises(Problem):
        local_directory(tmp_path)

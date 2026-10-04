import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from conftest import claim, import_files, project, save_body
from sqlalchemy import create_engine

from visionlabel.database import SCHEMA_REVISION, Database, row, rows
from visionlabel.domain import Problem, uid
from visionlabel.service import Service


def create_user(client, username="junior"):
    body = {"username": username, "display_name": "Junior ไทย", "password": "a-long-user-password"}
    response = client.post("/api/v1/users", json=body, headers={"Idempotency-Key": uid()})
    assert response.status_code == 201, response.text
    return response.json()


def member(client, proj, target, role, revision=1):
    return client.put(
        f"/api/v1/projects/{proj['id']}/members/{target['id']}",
        json={"role": role, "expected_project_revision": revision},
        headers={"Idempotency-Key": uid()},
    )


def test_accounts_are_private_and_creation_replays_without_password_storage(environment):
    client, srv, _ = environment
    body = {"username": "Junior", "display_name": "User", "password": "secret-for-new-account"}
    key = {"Idempotency-Key": uid()}
    response = client.post("/api/v1/users", json=body, headers=key)
    assert response.status_code == 201, response.text
    assert response.json()["username"] == "junior"
    assert client.post("/api/v1/users", json=body, headers=key).json() == response.json()
    assert (
        client.post(
            "/api/v1/users", json=dict(body, password="changed-long-password"), headers=key
        ).status_code
        == 409
    )
    assert client.post("/api/v1/users", json=body, headers={"Idempotency-Key": uid()}).status_code == 409
    assert "password" not in client.get("/api/v1/users").text
    with srv.db.engine.connect() as conn:
        persisted = json.dumps(
            rows(conn, "SELECT * FROM audit_events") + rows(conn, "SELECT * FROM idempotency_records")
        )
    assert body["password"] not in persisted
    token = srv.login("junior", body["password"])["token"]
    client.headers["Authorization"] = "Bearer " + token
    assert client.get("/api/v1/users").status_code == 403
    assert client.post("/api/v1/users", json=body, headers={"Idempotency-Key": uid()}).status_code == 403
    assert client.get("/api/v1/projects").json()["items"] == []
    assert client.get("/api/v1/me").json()["project_roles"] == []


def test_membership_permissions_revision_and_last_maintainer(environment):
    client, srv, _ = environment
    proj = project(client)
    admin = client.get("/api/v1/me").json()
    junior = create_user(client)
    assert member(client, proj, admin, "viewer").status_code == 409
    response = member(client, proj, junior, "annotator")
    assert response.status_code == 200, response.text
    assert response.json()["project_revision"] == 2
    assert member(client, proj, junior, "viewer").status_code == 409
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    assert member(client, proj, junior, "maintainer", 2).status_code == 403
    assert client.get(f"/api/v1/projects/{proj['id']}").json()["can_edit"] is True
    assert client.get(f"/api/v1/projects/{proj['id']}").json()["can_manage_members"] is False
    assert client.get("/api/v1/me").json()["project_roles"] == [
        {"project_id": proj["id"], "role": "annotator"}
    ]


def test_downgrade_during_save_fences_old_lease_and_preserves_head(environment):
    client, srv, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    junior = create_user(client)
    admin = srv.authenticate(client.headers["Authorization"][7:])
    assert member(client, proj, junior, "annotator").status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    lease = claim(client, image["id"])

    def revoke(point):
        if point == "after_publish":
            srv.change_member(
                admin,
                proj["id"],
                junior["id"],
                {"role": "viewer", "expected_project_revision": 2},
                uid(),
                uid(),
            )

    srv.fault = revoke
    response = client.put(
        f"/api/v1/images/{image['id']}/annotation",
        json=save_body(proj),
        headers=dict(lease, **{"Idempotency-Key": uid()}),
    )
    assert response.status_code == 403, response.text
    assert client.get(f"/api/v1/images/{image['id']}/annotation").json()["revision"] == 0
    assert client.get(f"/api/v1/projects/{proj['id']}").json()["can_edit"] is False
    with srv.db.engine.connect() as conn:
        current = row(conn, "SELECT * FROM task_claims WHERE image_id=?", (image["id"],))
        assert current["generation"] == int(lease["X-Claim-Generation"]) + 1


def test_remove_member_revokes_only_that_projects_claims(environment):
    client, srv, root = environment
    p1, p2 = project(client), project(client)
    i1, i2 = import_files(client, root, p1["id"])[0], import_files(client, root, p2["id"])[0]
    junior = create_user(client)
    admin_token = client.headers["Authorization"]
    for p in (p1, p2):
        assert member(client, p, junior, "annotator").status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    junior_token = client.headers["Authorization"]
    first, second = claim(client, i1["id"]), claim(client, i2["id"])
    client.headers["Authorization"] = admin_token
    path = f"/api/v1/projects/{p1['id']}/members/{junior['id']}"
    headers = {"Idempotency-Key": uid()}
    body = {"expected_project_revision": 2}
    assert client.request("DELETE", path, json=body, headers=headers).status_code == 204
    assert client.request("DELETE", path, json=body, headers=headers).status_code == 204
    client.headers["Authorization"] = junior_token
    assert client.get(f"/api/v1/images/{i1['id']}/content").status_code == 404
    assert client.post(f"/api/v1/images/{i1['id']}/claim/heartbeat", headers=first).status_code == 404
    assert client.post(f"/api/v1/images/{i2['id']}/claim/heartbeat", headers=second).status_code == 200


def test_password_reset_disable_and_reenable_do_not_resurrect_tokens(environment):
    client, srv, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    junior = create_user(client)
    admin_token = client.headers["Authorization"]
    assert member(client, proj, junior, "annotator").status_code == 200
    old_token = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    client.headers["Authorization"] = old_token
    lease = claim(client, image["id"])
    client.headers["Authorization"] = admin_token
    body = {"expected_user_revision": 1, "password": "replacement-password"}
    path = f"/api/v1/users/{junior['id']}"
    headers = {"Idempotency-Key": uid()}
    response = client.patch(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert client.patch(path, json=body, headers=headers).json() == response.json()
    client.headers["Authorization"] = old_token
    assert client.get("/api/v1/me").status_code == 401
    new_token = "Bearer " + srv.login("junior", "replacement-password")["token"]
    client.headers["Authorization"] = new_token
    assert client.post(f"/api/v1/images/{image['id']}/claim/heartbeat", headers=lease).status_code == 409
    client.headers["Authorization"] = admin_token
    assert (
        client.patch(
            path, json={"expected_user_revision": 2, "disabled": True}, headers={"Idempotency-Key": uid()}
        ).status_code
        == 200
    )
    assert (
        client.patch(
            path, json={"expected_user_revision": 3, "disabled": False}, headers={"Idempotency-Key": uid()}
        ).status_code
        == 200
    )
    client.headers["Authorization"] = new_token
    assert client.get("/api/v1/me").status_code == 401


def test_concurrent_membership_updates_have_one_winner(environment):
    client, srv, _ = environment
    proj, junior = project(client), create_user(client)
    admin = srv.authenticate(client.headers["Authorization"][7:])
    barrier = Barrier(2)

    def change(role):
        barrier.wait()
        try:
            return srv.change_member(
                admin, proj["id"], junior["id"], {"role": role, "expected_project_revision": 1}, uid(), uid()
            )["project_revision"]
        except Problem as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(change, ["annotator", "viewer"]))
    assert sorted(map(str, outcomes)) == ["2", "REVISION_CONFLICT"]
    with srv.db.engine.connect() as conn:
        assert len(rows(conn, "SELECT * FROM audit_events WHERE action='membership.updated'")) == 1


def test_last_admin_and_last_active_maintainer_are_protected(environment):
    client, _, _ = environment
    admin = client.get("/api/v1/me").json()
    assert (
        client.patch(
            f"/api/v1/users/{admin['id']}",
            json={"expected_user_revision": 1, "disabled": True},
            headers={"Idempotency-Key": uid()},
        ).json()["error"]["code"]
        == "LAST_ADMIN"
    )
    proj, junior = project(client), create_user(client)
    assert member(client, proj, junior, "maintainer").status_code == 200
    assert member(client, proj, admin, "viewer", 2).status_code == 200
    response = client.patch(
        f"/api/v1/users/{junior['id']}",
        json={"expected_user_revision": 1, "disabled": True},
        headers={"Idempotency-Key": uid()},
    )
    assert response.json()["error"]["code"] == "LAST_MAINTAINER"


def test_migration_preserves_phase1_records(tmp_path):
    from alembic import command
    from alembic.config import Config

    import visionlabel.database as module

    root = tmp_path / "server"
    root.mkdir()
    dbdir = root / "db"
    dbdir.mkdir()
    path = dbdir / "data_tracking.sqlite3"
    engine = create_engine("sqlite:///" + path.as_posix())
    config = Config()
    from pathlib import Path

    config.set_main_option("script_location", str(Path(module.__file__).parent / "migrations"))
    with engine.begin() as conn:
        config.attributes["connection"] = conn
        command.upgrade(config, "0001")
        conn.exec_driver_sql(
            "INSERT INTO users (id,username,display_name,password_hash,is_admin,created_at) VALUES ('old','old','Original','preserved',1,'2026-01-01')"
        )
    engine.dispose()
    db = Database(path)
    db.migrate()
    with db.engine.connect() as conn:
        record = row(conn, "SELECT * FROM users WHERE id='old'")
        assert record["display_name"] == "Original" and record["password_hash"] == "preserved"
        assert record["user_revision"] == 1
        assert conn.exec_driver_sql("SELECT version_num FROM alembic_version").scalar() == SCHEMA_REVISION
    db.engine.dispose()
    service = Service(root)
    service.close()

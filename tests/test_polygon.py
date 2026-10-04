import copy
import json
from pathlib import Path

import pytest
from conftest import claim, import_files, project, save_body
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from visionlabel.api import create_app
from visionlabel.database import Database, row, rows
from visionlabel.domain import Editor, Problem, canonical, digest, uid, validate_content
from visionlabel.polygon_canvas import PolygonCanvas, inside_polygon
from visionlabel.service import Service

CLASS = "10000000-0000-4000-8000-000000000001"
SHAPE = "20000000-0000-4000-8000-000000000001"


def polygon(points, class_id=CLASS):
    return {"id": SHAPE, "type": "polygon", "class_id": class_id, "points": points, "attributes": {}}


def content(points):
    return {"verified_empty": False, "image_labels": [], "shapes": [polygon(points)]}


def test_polygon_exact_bytes_independent_of_winding_and_start():
    points = [[10, 20], [80, 20], [80, 90], [10, 90]]
    golden = b'{"attributes":{},"class_id":"10000000-0000-4000-8000-000000000001","id":"20000000-0000-4000-8000-000000000001","points":[[10,20],[80,20],[80,90],[10,90]],"type":"polygon"}'
    for ring in (points, list(reversed(points)), points[2:] + points[:2]):
        normalized = validate_content(content(ring), 100, 100, "segmentation", {CLASS})
        assert canonical(normalized["shapes"][0]) == golden


@pytest.mark.parametrize(
    "points",
    [
        None,
        "bad",
        [[1, 2], [3, 4]],
        [[0, 0], [10, 0], [20, 0]],
        [[0, 0], [10, 0], [10, 10], [0, 0]],
        [[10, 10], [90, 80], [10, 90], [80, 10]],
        [[-1, 0], [10, 0], [0, 10]],
        [[0, 0], [0.0000001, 0], [0, 10]],
        [[True, 0], [10, 0], [0, 10]],
    ],
)
def test_polygon_invalid_geometry_rejected(points):
    with pytest.raises(Problem):
        validate_content(content(points), 100, 100, "segmentation", {CLASS})


def make_canvas():
    canvas = PolygonCanvas(Editor())
    canvas.width = canvas.height = 100
    return canvas


def draw_square(canvas):
    for x, y in [(10, 10), (70, 10), (70, 70), (10, 70)]:
        canvas.start(*canvas.transform.screen(x, y), CLASS)
        canvas.finish()  # Releasing each click must not commit an unfinished polygon.
    assert canvas.editor.content["shapes"] == []
    canvas.finish_polygon()


@pytest.mark.parametrize("scale", [0.25, 1, 1.5, 4])
def test_polygon_editing_and_screen_sized_handles(scale):
    canvas = make_canvas()
    canvas.transform.scale = scale
    draw_square(canvas)
    canvas.mode = "select"
    sx, sy = canvas.transform.screen(70, 70)
    canvas.start(sx + 3, sy + 3, CLASS)
    assert canvas.gesture["kind"] == "vertex"
    canvas.move(*canvas.transform.screen(80, 80))
    canvas.finish()
    assert [80, 80] in canvas.editor.content["shapes"][0]["points"]
    canvas.editor.undo()
    assert [70, 70] in canvas.editor.content["shapes"][0]["points"]
    canvas.editor.redo()
    assert [80, 80] in canvas.editor.content["shapes"][0]["points"]
    canvas.selected_vertex = None
    canvas.start(*canvas.transform.screen(35, 35), CLASS)
    canvas.move(*canvas.transform.screen(100, 100))
    canvas.finish()
    points = canvas.editor.content["shapes"][0]["points"]
    assert max(x for x, y in points) == max(y for x, y in points) == 100


def test_polygon_cancel_pan_invalid_move_and_vertex_insert_delete():
    canvas = make_canvas()
    canvas.start(10, 10, CLASS)
    canvas.start(20, 10, CLASS)
    canvas.start(50, 50, CLASS, pan=True)
    canvas.move(55, 60)
    canvas.finish()
    assert canvas.draft == [[10, 10], [20, 10]]
    assert not canvas.editor.dirty
    canvas.cancel()
    assert canvas.draft == []
    draw_square(canvas)
    canvas.mode = "select"
    canvas.insert_vertex(*canvas.transform.screen(40, 10))
    assert len(canvas.editor.content["shapes"][0]["points"]) == 5
    canvas.start(*canvas.transform.screen(40, 10), CLASS)
    canvas.finish()
    assert canvas.delete_vertex()
    assert len(canvas.editor.content["shapes"][0]["points"]) == 4
    baseline = copy.deepcopy(canvas.editor.content)
    canvas.start(*canvas.transform.screen(70, 10), CLASS)
    canvas.move(*canvas.transform.screen(40, 90))
    with pytest.raises(Problem):
        canvas.finish()
    assert canvas.editor.content == baseline
    assert canvas.preview is None
    assert inside_polygon(20, 20, [[10, 10], [50, 10], [50, 50], [10, 50]])
    assert not inside_polygon(0, 0, [[10, 10], [50, 10], [50, 50], [10, 50]])


def test_invalid_draft_stays_local_until_corrected():
    canvas = make_canvas()
    for point in [(10, 10), (90, 80), (10, 90), (80, 10)]:
        canvas.start(*point, CLASS)
    with pytest.raises(Problem):
        canvas.finish_polygon()
    assert len(canvas.draft) == 4 and not canvas.editor.dirty
    canvas.draft.pop()
    canvas.finish_polygon()
    assert len(canvas.editor.content["shapes"][0]["points"]) == 3
    canvas.selected_vertex = 0
    with pytest.raises(Problem):
        canvas.delete_vertex()


def test_segmentation_save_reload_schema_and_invalid_api_points(environment):
    client, srv, root = environment
    proj = project(client, "segmentation")
    image = import_files(client, root, proj["id"])[0]
    headers = dict(claim(client, image["id"]), **{"Idempotency-Key": uid()})
    body = save_body(proj)
    body["content"]["shapes"] = [
        polygon([[80, 90], [80, 20], [10, 20], [10, 90]], proj["schema"]["entries"][0]["class_id"])
    ]
    path = f"/api/v1/images/{image['id']}/annotation"
    response = client.put(path, json=body, headers=headers)
    assert response.status_code == 200, response.text
    loaded = client.get(path).json()
    assert loaded["annotation"]["shapes"][0]["points"] == [[10, 20], [80, 20], [80, 90], [10, 90]]
    schema = json.loads(
        (Path(__file__).parents[1] / "src/visionlabel/schemas/annotation-1.0.0.json").read_text()
    )
    Draft202012Validator(schema).validate(loaded["annotation"])
    body["expected_revision"] = body["expected_state_revision"] = 1
    body["content"]["shapes"][0]["points"] = None
    headers["Idempotency-Key"] = uid()
    assert client.put(path, json=body, headers=headers).status_code == 422
    assert client.get(path).json()["revision"] == 1


def test_working_statistics_counts_saved_labels_and_detects_corruption(environment):
    client, srv, root = environment
    proj = project(client)
    images = import_files(client, root, proj["id"], 3)
    body = save_body(proj)
    tiny = copy.deepcopy(body["content"]["shapes"][0])
    tiny.update(id=uid(), x1=0, y1=0, x2=1, y2=1)
    body["content"]["shapes"].append(tiny)
    other = copy.deepcopy(tiny)
    other.update(id=uid(), class_id=proj["schema"]["entries"][1]["class_id"], x2=5, y2=5)
    body["content"]["shapes"].append(other)
    for index, item in enumerate(images[:2]):
        if index:
            body["content"] = {"shapes": [], "image_labels": [], "verified_empty": True}
        response = client.put(
            f"/api/v1/images/{item['id']}/annotation",
            json=body,
            headers=dict(claim(client, item["id"]), **{"Idempotency-Key": uid()}),
        )
        assert response.status_code == 200, response.text
    path = f"/api/v1/projects/{proj['id']}/statistics"
    result = client.get(path).json()
    assert result["total_images"] == 3 and result["verified_empty_images"] == 1
    assert sorted((c["image_count"], c["object_count"]) for c in result["classes"]) == [
        (0, 0),
        (1, 1),
        (1, 2),
    ]
    assert [w["code"] for w in result["warnings"]].count("TINY_SHAPE") == 1
    assert [w["code"] for w in result["warnings"]].count("UNLABELED") == 1
    assert result["source_revision"] == client.get(path).json()["source_revision"]
    with srv.db.engine.connect() as conn:
        artifact = row(
            conn, "SELECT blob_path FROM annotation_revisions WHERE image_id=?", (images[0]["id"],)
        )
    (srv.blobs.root / artifact["blob_path"]).write_bytes(b"corrupt synthetic test")
    assert client.get(path).status_code == 503


def test_upgrade_from_phase2_preserves_project_and_annotation_bytes(tmp_path, monkeypatch):
    from alembic import command
    from alembic.config import Config

    import visionlabel.database as database_module

    def migrate_phase2(db):
        config = Config()
        config.set_main_option("script_location", str(Path(database_module.__file__).parent / "migrations"))
        with db.engine.begin() as conn:
            config.attributes["connection"] = conn
            command.upgrade(config, "0002")

    root = tmp_path / "server"
    tables = (
        "projects",
        "classes",
        "class_schemas",
        "class_schema_entries",
        "assets",
        "images",
        "annotation_heads",
        "annotation_revisions",
        "project_members",
    )
    with monkeypatch.context() as patch:
        patch.setattr(Database, "migrate", migrate_phase2)
        old = Service(root)
        old.bootstrap("admin", "migration-test-password")
        old.close()
        with TestClient(create_app(root)) as client:
            login = client.post(
                "/api/v1/auth/login", json={"username": "admin", "password": "migration-test-password"}
            ).json()
            client.headers["Authorization"] = "Bearer " + login["token"]
            proj = project(client)
            image = import_files(client, root, proj["id"])[0]
            result = client.put(
                f"/api/v1/images/{image['id']}/annotation",
                json=save_body(proj),
                headers=dict(claim(client, image["id"]), **{"Idempotency-Key": uid()}),
            )
            assert result.status_code == 200
            old = client.app.state.service
            with old.db.engine.connect() as conn:
                before = {table: rows(conn, f"SELECT * FROM {table}") for table in tables}
            reference = before["annotation_revisions"][0]
            artifact = old.blobs.read(reference["blob_path"], reference["sha256"])
    upgraded = Service(root)
    try:
        with upgraded.db.engine.connect() as conn:
            assert {table: rows(conn, f"SELECT * FROM {table}") for table in tables} == before
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").fetchall() == []
        assert upgraded.blobs.read(reference["blob_path"], reference["sha256"]) == artifact
        assert digest(artifact) == reference["sha256"]
    finally:
        upgraded.close()

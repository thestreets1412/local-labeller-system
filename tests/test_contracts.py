import json
from pathlib import Path

import pytest
from conftest import claim, import_files, project, save_body
from jsonschema import Draft202012Validator, FormatChecker

from visionlabel.domain import uid


def test_saved_document_matches_spec_json_schema(environment):
    client, service, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    lease = claim(client, image["id"])
    assert (
        client.put(
            f"/api/v1/images/{image['id']}/annotation",
            json=save_body(proj),
            headers=dict(lease, **{"Idempotency-Key": uid()}),
        ).status_code
        == 200
    )
    doc = client.get(f"/api/v1/images/{image['id']}/annotation").json()["annotation"]
    schema = json.loads(
        (Path(__file__).parents[1] / "src/visionlabel/schemas/annotation-1.0.0.json").read_text()
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    validator.validate(doc)
    doc["image_id"] = "invalid"
    assert list(validator.iter_errors(doc))


def test_openapi_does_not_load_external_documentation(environment):
    client, _, _ = environment
    assert client.get("/docs").status_code == 404
    assert client.get("/redoc").status_code == 404
    contract = client.get("/openapi.json")
    assert contract.status_code == 200
    assert "/api/v1/images/{image_id}/annotation" in contract.json()["paths"]
    assert client.get("/api/v1/health/ready").json()["status"] == "ready"


def test_coordinate_rounding_preserves_request_decimal_text(environment):
    client, _, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    lease = claim(client, image["id"])
    raw = json.dumps(save_body(proj)).replace('"x1": 10,', '"x1": 10.000000500000000000001,')
    path = f"/api/v1/images/{image['id']}/annotation"
    response = client.put(
        path,
        content=raw,
        headers=dict(lease, **{"Idempotency-Key": uid(), "Content-Type": "application/json"}),
    )
    assert response.status_code == 200, response.text
    assert client.get(path).json()["annotation"]["shapes"][0]["x1"] == 10.000001


@pytest.mark.parametrize("ratio", [1, 1.25, 1.5, 2])
def test_resize_handle_hit_target_is_screen_sized(ratio):
    from visionlabel.canvas import Canvas
    from visionlabel.domain import Editor

    editor = Editor()
    canvas = Canvas(editor)
    canvas.width = canvas.height = 500
    canvas.start(50, 60, uid())
    canvas.move(180, 220)
    canvas.finish()
    canvas.transform.scale = ratio
    sx, sy = canvas.transform.screen(180, 220)
    canvas.start(sx + 6, sy + 6, uid())
    assert canvas.gesture["kind"] == "resize"

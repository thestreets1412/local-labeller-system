import copy
from decimal import Decimal

import pytest

from visionlabel.canvas import Canvas
from visionlabel.domain import Editor, Problem, Transform, canonical, uid, validate_content


def test_canonical_exact_bytes():
    assert (
        canonical({"z": -0.0, "a": Decimal("1.0000005"), "b": Decimal("1.0000015"), "c": "ไทย"})
        == b'{"a":1,"b":1.000002,"c":"\xe0\xb9\x84\xe0\xb8\x97\xe0\xb8\xa2","z":0}'
    )
    for number in [float("nan"), float("inf"), -float("inf")]:
        with pytest.raises(Problem):
            canonical(number)


def test_rectangle_rounding_and_bounds():
    cls = uid()
    shape = {
        "id": uid(),
        "type": "rectangle",
        "class_id": cls,
        "x1": 10,
        "y1": 20,
        "x2": 50,
        "y2": 100,
        "attributes": {},
    }
    content = {"verified_empty": False, "image_labels": [], "shapes": [shape]}
    assert validate_content(content, 100, 200, "detection", {cls})["shapes"][0]["x1"] == 10
    for key, value in [("x1", -1), ("x2", 101), ("y2", 201), ("x2", 10.0000001), ("x1", True)]:
        invalid = copy.deepcopy(content)
        invalid["shapes"][0][key] = value
        with pytest.raises(Problem):
            validate_content(invalid, 100, 200, "detection", {cls})
    with pytest.raises(Problem):
        validate_content(
            {"verified_empty": False, "image_labels": [], "shapes": []},
            100,
            200,
            "detection",
            {cls},
            complete=True,
        )


@pytest.mark.parametrize("scale", [0.15, 1, 1.25, 1.5, 2, 8])
def test_transforms_and_cursor_zoom(scale):
    transform = Transform(scale, 123, -47)
    assert transform.pixel(*transform.screen(50, 70)) == pytest.approx((50, 70))
    before = transform.pixel(350, 270)
    transform.zoom(350, 270, 1.15)
    assert transform.pixel(350, 270) == pytest.approx(before)


@pytest.mark.parametrize(
    "start,end", [((10, 20), (50, 100)), ((50, 20), (10, 100)), ((50, 100), (10, 20)), ((10, 100), (50, 20))]
)
def test_rectangle_gestures_undo_and_resize(start, end):
    editor = Editor()
    canvas = Canvas(editor)
    canvas.width, canvas.height = 100, 200
    canvas.start(*start, uid())
    canvas.move(*end)
    canvas.finish()
    shape = editor.content["shapes"][0]
    assert [shape[k] for k in ("x1", "y1", "x2", "y2")] == [10, 20, 50, 100]
    editor.undo()
    assert editor.content["shapes"] == []
    editor.redo()
    canvas.mode = "select"
    canvas.start(30, 60, shape["class_id"])
    canvas.move(500, 500)
    canvas.finish()
    shape = editor.content["shapes"][0]
    assert (shape["x2"], shape["y2"]) == (100, 200)
    canvas.start(100, 200, shape["class_id"])
    canvas.move(90, 190)
    canvas.finish()
    shape = editor.content["shapes"][0]
    assert (shape["x2"], shape["y2"]) == (90, 190)


def test_classification_and_empty_distinction():
    cls = uid()
    content = {"verified_empty": False, "image_labels": [cls], "shapes": []}
    assert validate_content(content, 10, 10, "classification", {cls}, True) == content
    with pytest.raises(Problem):
        validate_content(dict(content, verified_empty=True), 10, 10, "classification", {cls})


def test_domain_has_no_infrastructure_dependencies():
    import ast
    from pathlib import Path

    tree = ast.parse((Path(__file__).parents[1] / "src/visionlabel/domain.py").read_text())
    imports = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)]
    assert not any(
        name and name.split(".")[0] in {"dearpygui", "fastapi", "sqlalchemy", "httpx"} for name in imports
    )

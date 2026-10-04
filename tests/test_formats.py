import copy
import json
import re
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

import pytest

from visionlabel.domain import Problem, canonical, empty_content
from visionlabel.fixtures import png_bytes
from visionlabel.format_preview import dry_run, export_preview
from visionlabel.formats import classification_mapping, yolo_config, yolo_labels
from visionlabel.legacy import parse_labelme, parse_yolo

A = "10000000-0000-4000-8000-000000000001"
B = "10000000-0000-4000-8000-000000000002"
IMAGE = "20000000-0000-4000-8000-000000000001"
SHAPE = "30000000-0000-4000-8000-000000000001"
CLASSES = [
    {"class_id": B, "export_index": 0, "name": "NG", "key": "ng"},
    {"class_id": A, "export_index": 2, "name": "OK", "key": "ok"},
    {
        "class_id": "10000000-0000-4000-8000-000000000003",
        "export_index": 1,
        "name": "Retired",
        "key": "retired",
        "active": False,
    },
]


def rectangle(**kwargs):
    shape = {
        "id": SHAPE,
        "type": "rectangle",
        "class_id": A,
        "attributes": {},
        "x1": 10,
        "y1": 20,
        "x2": 30,
        "y2": 60,
    }
    shape.update(kwargs)
    return {"verified_empty": False, "image_labels": [], "shapes": [shape]}


def polygon(points=None):
    return {
        "verified_empty": False,
        "image_labels": [],
        "shapes": [
            {
                "id": SHAPE,
                "type": "polygon",
                "class_id": A,
                "attributes": {},
                "points": points or [[10, 20], [30, 20], [30, 60]],
            }
        ],
    }


def test_detection_golden_and_independent_inverse():
    data, warnings = yolo_labels(rectangle(), 100, 200, "detection", CLASSES)
    assert data == b"2 0.200000000 0.200000000 0.200000000 0.200000000\n"
    assert not warnings
    fields = data.decode().strip().split()
    assert fields[0] == "2"  # Deliberately differs from schema array position.
    assert all(re.fullmatch(r"[01]\.\d{9}", v) for v in fields[1:])
    cx, cy, w, h = map(Decimal, fields[1:])
    assert ((cx - w / 2) * 100, (cy - h / 2) * 200, (cx + w / 2) * 100, (cy + h / 2) * 200) == (
        10,
        20,
        30,
        60,
    )


def test_fractional_roundtrip_error_bound():
    source = rectangle(
        x1=Decimal("1.234567"), y1=Decimal("5.234567"), x2=Decimal("319.999999"), y2=Decimal("200.123456")
    )
    data, _ = yolo_labels(source, 641, 401, "detection", CLASSES)
    _, cx, cy, w, h = data.decode().split()
    cx, cy, w, h = map(Decimal, (cx, cy, w, h))
    recovered = [(cx - w / 2) * 641, (cy - h / 2) * 401, (cx + w / 2) * 641, (cy + h / 2) * 401]
    for value, key in zip(recovered, ("x1", "y1", "x2", "y2"), strict=True):
        assert abs(value - source["shapes"][0][key]) <= Decimal("0.00000075") * 641


def test_segmentation_golden_and_explicit_loss():
    data, warnings = yolo_labels(polygon(), 100, 200, "segmentation", CLASSES)
    assert data == b"2 0.100000000 0.100000000 0.300000000 0.100000000 0.300000000 0.300000000\n"
    assert not warnings
    data, warnings = yolo_labels(
        polygon(), 100, 200, "segmentation", CLASSES, polygon_to_bbox=True, image_id=IMAGE
    )
    assert data == b"2 0.200000000 0.200000000 0.200000000 0.200000000\n"
    assert warnings == [{"code": "POLYGON_TO_BBOX_LOSS", "image_id": IMAGE, "shape_id": SHAPE}]
    with pytest.raises(Problem):
        yolo_labels(rectangle(), 100, 200, "segmentation", CLASSES)


@pytest.mark.parametrize(
    "content,task",
    [
        (rectangle(x1=1, x2=1.000001, y1=1, y2=2), "detection"),
        (polygon([[1, 1], [1.000001, 1], [1, 2]]), "segmentation"),
    ],
)
def test_quantization_collapse_reports_identity(content, task):
    with pytest.raises(Problem) as error:
        yolo_labels(content, 10000, 1000, task, CLASSES, image_id=IMAGE)
    assert error.value.code == "UNREPRESENTABLE_GEOMETRY"
    assert error.value.details == {"image_id": IMAGE, "shape_id": SHAPE}


def test_rounding_cannot_push_box_out_of_bounds():
    # Width rounds to 1/3, center to 1/6: left edge becomes negative.
    with pytest.raises(Problem, match="quantization"):
        yolo_labels(rectangle(x1=0, x2=2, y1=0, y2=2), 3, 3, "detection", CLASSES)


def test_verified_empty_and_unlabeled():
    content = empty_content()
    with pytest.raises(Problem):
        yolo_labels(content, 100, 200, "detection", CLASSES)
    content["verified_empty"] = True
    assert yolo_labels(content, 100, 200, "detection", CLASSES)[0] == b""
    for text, option, expected in [(None, True, False), ("", False, False), ("", True, True)]:
        result, state = parse_yolo(
            text, 100, 200, {"2": A}, source_identity="fixture", empty_is_verified=option
        )
        assert result["verified_empty"] is expected
        assert state == ("ANNOTATED" if expected else "UNLABELED")


@pytest.mark.parametrize(
    "text",
    [
        "2 .5 .5 0 .1",
        "2 nan .5 .1 .1",
        "2 inf .5 .1 .1",
        "2 .99 .5 .1 .1",
        "2.0 .5 .5 .1 .1",
        "3 .5 .5 .1 .1",
        "2 .5 .5 .1 .1 extra",
        "2 .5 .5 -.1 .1",
        "2 .5 .5 1e-100 .1",
    ],
)
def test_bad_yolo_never_silently_drops(text):
    with pytest.raises(Problem):
        parse_yolo(text, 100, 200, {"2": A}, source_identity="fixture")


def test_legacy_yolo_coordinates_and_stable_ids():
    args = ("2 .2 .2 .2 .2\n", 100, 200, {"2": A})
    content, state = parse_yolo(*args, source_identity="fixture")
    assert state == "ANNOTATED"
    assert [content["shapes"][0][key] for key in ("x1", "y1", "x2", "y2")] == [10, 20, 30, 60]
    assert content == parse_yolo(*args, source_identity="fixture")[0]
    assert content != parse_yolo(*args, source_identity="other-source")[0]


def labelme():
    return {
        "version": "5.0",
        "imagePath": "image.png",
        "imageWidth": 100,
        "imageHeight": 200,
        "imageData": None,
        "shapes": [
            {
                "label": "good",
                "shape_type": "rectangle",
                "points": [[30, 60], [10, 20]],
                "flags": {},
                "group_id": None,
            }
        ],
    }


def test_labelme_reversed_rectangle_and_empty():
    doc = labelme()
    content, state = parse_labelme(doc, 100, 200, "detection", {"good": A}, source_identity="fixture")
    assert state == "ANNOTATED"
    assert [content["shapes"][0][k] for k in ("x1", "y1", "x2", "y2")] == [10, 20, 30, 60]
    doc["shapes"] = []
    assert parse_labelme(doc, 100, 200, "detection", {"good": A}, source_identity="fixture") == (
        empty_content(),
        "UNLABELED",
    )


@pytest.mark.parametrize(
    "change",
    ["circle", "line", "point", "unmapped", "dimensions", "embedded", "group", "flags", "self-intersection"],
)
def test_labelme_rejects_unsupported_or_ambiguous_data(change):
    doc = labelme()
    task = "detection"
    if change in ("circle", "line", "point"):
        doc["shapes"][0]["shape_type"] = change
    elif change == "unmapped":
        doc["shapes"][0]["label"] = "other"
    elif change == "dimensions":
        doc["imageWidth"] = 99
    elif change == "embedded":
        doc["imageData"] = "abcd"
    elif change == "group":
        doc["shapes"][0]["group_id"] = 1
    elif change == "flags":
        doc["flags"] = {"flag": True}
    else:
        task = "segmentation"
        doc["shapes"][0].update(shape_type="polygon", points=[[1, 1], [10, 10], [1, 10], [10, 1]])
    with pytest.raises(Problem):
        parse_labelme(doc, 100, 200, task, {"good": A}, source_identity="fixture")


def test_classification_mapping_order_coverage_and_windows_names():
    classes = copy.deepcopy(CLASSES[:2])
    classes[0]["export_index"] = 9
    classes[0]["key"] = "CON/..:ไทย"
    rows = classification_mapping(classes, {A, B}, {B})
    assert rows[0] == {
        "folder_name": "0002_ok",
        "internal_class_id": A,
        "schema_export_index": 2,
        "consumer_order": 0,
    }
    assert rows[1]["folder_name"] == "0009_con"
    with pytest.raises(Problem) as error:
        classification_mapping(classes, {A}, {B})
    assert error.value.code == "TRAIN_COVERAGE"


def test_config_quotes_names_and_omits_disabled_partitions():
    classes = copy.deepcopy(CLASSES)
    classes[1]["name"] = 'ไทย: "ok"\ntrain: hacked'
    raw, warnings = yolo_config(classes, has_val=False, has_test=False)
    assert raw.decode().splitlines() == [
        "path: .",
        "train: images/train",
        "names:",
        '  0: "NG"',
        '  1: "Retired"',
        '  2: "ไทย: \\"ok\\"\\ntrain: hacked"'.replace("\\\\", "\\"),
    ]
    assert len(warnings) == 1


def preview_request():
    return {
        "task": "detection",
        "classes": copy.deepcopy(CLASSES),
        "items": [
            {"image_id": IMAGE, "partition": "train", "width": 100, "height": 200, "content": rectangle()}
        ],
    }


def test_preview_is_explicitly_noncanonical_and_deterministic():
    source = preview_request()
    report = export_preview(source)
    assert report["canonical_export"] is False and report["provenance_verified"] is False
    source["classes"].reverse()
    assert canonical(export_preview(source)) == canonical(report)


def test_dry_run_real_image_containment_and_per_file_errors(tmp_path):
    (tmp_path / "image.png").write_bytes(png_bytes(width=100, height=200))
    (tmp_path / "ok.json").write_text(json.dumps(labelme()), encoding="utf-8")
    bad = labelme()
    bad["imagePath"] = "../outside.png"
    (tmp_path / "bad.json").write_text(json.dumps(bad), encoding="utf-8")
    request = {
        "format": "labelme",
        "task": "detection",
        "mapping": {"good": A},
        "items": [
            {"image": "image.png", "label": "ok.json"},
            {"image": "image.png", "label": "bad.json"},
            {"image": "../outside.png", "label": "ok.json"},
        ],
    }
    report = dry_run(tmp_path, request)
    assert report["valid_count"] == 1 and report["error_count"] == 2
    assert report["files"][1]["error"]["code"] == "INVALID_PATH"
    assert report["canonical_import"] is False and report["database_conflicts_checked"] is False
    assert report["files"][0]["proposed_state"] == "ANNOTATED"


def test_preview_cli_no_overwrite(tmp_path):
    source, target = tmp_path / "input.json", tmp_path / "report.json"
    source.write_bytes(canonical(preview_request()))
    command = [
        sys.executable,
        "-m",
        "visionlabel.format_preview",
        "export-preview",
        "--input",
        str(source),
        "--output",
        str(target),
    ]
    first = subprocess.run(command, capture_output=True)
    assert first.returncode == 0, first.stderr
    before = target.read_bytes()
    assert subprocess.run(command, capture_output=True).returncode == 1
    assert target.read_bytes() == before


def test_example_fixture():
    source = Path(__file__).parent / "fixtures" / "formats" / "export-preview.json"
    request = json.loads(source.read_text(encoding="utf-8"))
    assert (
        export_preview(request)["files"][0]["label_text"]
        == "2 0.200000000 0.200000000 0.200000000 0.200000000\n"
    )


def test_yolo_config_requires_historical_slots():
    with pytest.raises(Problem) as error:
        yolo_config(CLASSES[:2])
    assert error.value.code == "INCOMPLETE_SCHEMA"
    assert b'  1: "Retired"\n' in yolo_config(CLASSES)[0]


def test_dry_run_yolo_missing_empty_and_invalid_sources(tmp_path):
    (tmp_path / "image.png").write_bytes(png_bytes(width=100, height=200))
    (tmp_path / "empty.txt").write_bytes(b"")
    (tmp_path / "invalid.txt").write_bytes(b"0 .5 .5 -1 .5")
    request = {
        "format": "yolo-detection",
        "task": "detection",
        "mapping": {"0": A},
        "empty_is_verified": True,
        "items": [
            {"image": "image.png", "label": name} for name in ("missing.txt", "empty.txt", "invalid.txt")
        ],
    }
    report = dry_run(tmp_path, request)
    assert report["valid_count"] == 2 and report["error_count"] == 1
    assert report["files"][0]["proposed_state"] == "UNLABELED"
    assert report["files"][1]["content"]["verified_empty"] is True
    assert "content" not in report["files"][2]
    source = tmp_path / "request.json"
    source.write_bytes(canonical(request))
    command = [
        sys.executable,
        "-m",
        "visionlabel.format_preview",
        "import-dry-run",
        "--source-root",
        str(tmp_path),
        "--input",
        str(source),
        "--output",
        str(tmp_path / "report.json"),
    ]
    assert subprocess.run(command, capture_output=True).returncode == 2


def test_classification_preview_rejects_multilabel():
    request = preview_request()
    request["task"] = "classification"
    request["items"][0]["content"] = {"verified_empty": False, "image_labels": [A, B], "shapes": []}
    with pytest.raises(Problem):
        export_preview(request)


def test_unknown_labelme_metadata_is_reported():
    doc = labelme()
    doc["shapes"][0]["mask"] = "unhandled payload"
    with pytest.raises(Problem) as error:
        parse_labelme(doc, 100, 200, "detection", {"good": A}, source_identity="fixture")
    assert error.value.code == "UNSUPPORTED_METADATA"

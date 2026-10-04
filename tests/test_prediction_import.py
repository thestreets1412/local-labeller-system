import json
import struct
import time

import pytest
from conftest import claim, project

from visionlabel.domain import Problem, uid
from visionlabel.fixtures import bmp_bytes
from visionlabel.imaging import decode, image_header


def options(proj, empty=False):
    return {
        "class_schema_id": proj["active_schema_id"],
        "class_mapping": {"0": proj["schema"]["entries"][1]["class_id"]},
        "empty_is_verified": empty,
    }


def submit(client, proj, yolo, paths=None, dry_run=False):
    response = client.post(
        f"/api/v1/projects/{proj['id']}/imports",
        json={"relative_paths": paths or ["spring_img.bmp"], "dry_run": dry_run, "yolo": yolo},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 202, response.text
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{response.json()['job_id']}").json()
        if job["state"] in ("succeeded", "failed"):
            assert job["state"] == "succeeded", job
            return job["result"]["items"]
        time.sleep(0.01)
    pytest.fail("Import job timeout")


@pytest.mark.parametrize("top_down", [False, True])
def test_bmp_original_raster_and_padding(tmp_path, top_down):
    raw = bmp_bytes(3, 2, top_down)
    assert image_header(raw) == (3, 2, "bmp")
    path = tmp_path / "ภาพ.BMP"
    path.write_bytes(raw)
    width, height, pixels, extension = decode(path)
    assert (width, height, extension) == (3, 2, "bmp")
    assert pixels[:12] == bytes((255, 0, 0, 255)) * 3
    assert pixels[12:] == bytes((0, 0, 255, 255)) * 3


def test_prediction_preview_import_edit_reload_and_provenance(environment):
    client, service, root = environment
    proj = project(client)
    raw = bmp_bytes()
    (root / "inbox/spring_img.bmp").write_bytes(raw)
    (root / "inbox/spring_img.txt").write_text("0 0.2 0.2 0.2 0.2\n", encoding="utf-8")
    assert client.get(f"/api/v1/projects/{proj['id']}/import-sources").json()["relative_paths"] == [
        "spring_img.bmp"
    ]
    preview = submit(client, proj, options(proj), dry_run=True)[0]
    assert preview["shape_count"] == 1 and preview["outcome"] == "new"
    assert client.get(f"/api/v1/projects/{proj['id']}/images").json()["items"] == []
    result = submit(client, proj, options(proj))[0]
    assert result["label_state"] == "IN_PROGRESS" and result["revision"] == 1
    image_id = result["image_id"]
    loaded = client.get(f"/api/v1/images/{image_id}/annotation").json()
    shape = loaded["annotation"]["shapes"][0]
    assert [shape[k] for k in ("x1", "y1", "x2", "y2")] == [10, 20, 30, 60]
    assert shape["class_id"] == proj["schema"]["entries"][1]["class_id"]
    with service.db.engine.connect() as conn:
        asset = conn.exec_driver_sql("SELECT blob_path,media_type FROM assets").first()
        assert asset[1] == "image/bmp"
        assert (root / "managed" / asset[0]).read_bytes() == raw
        audits = conn.exec_driver_sql(
            "SELECT detail_json FROM audit_events WHERE action='annotation.saved'"
        ).all()
        assert json.loads(audits[0][0])["import"]["label_sha256"] == result["label_sha256"]
    lease = claim(client, image_id)
    content = {k: loaded["annotation"][k] for k in ("shapes", "image_labels", "verified_empty")}
    content["shapes"][0]["x2"] = 40
    saved = client.put(
        f"/api/v1/images/{image_id}/annotation",
        json={
            "expected_revision": 1,
            "expected_state_revision": 1,
            "class_schema_id": proj["active_schema_id"],
            "content": content,
        },
        headers=dict(lease, **{"Idempotency-Key": uid()}),
    )
    assert saved.status_code == 200, saved.text
    assert client.get(f"/api/v1/images/{image_id}/annotation").json()["annotation"]["shapes"][0]["x2"] == 40
    repeated = submit(client, proj, options(proj))[0]
    assert repeated["code"] == "ANNOTATION_EXISTS"
    assert client.get(f"/api/v1/images/{image_id}/annotation").json()["annotation"]["revision"] == 2


@pytest.mark.parametrize(
    "label,empty,expected",
    [
        (None, True, "UNLABELED"),
        ("", False, "UNLABELED"),
        ("", True, "IN_PROGRESS"),
        ("0 .5 .5 -.1 .2", False, "invalid"),
        ("4 .5 .5 .1 .2", False, "invalid"),
        ("0 .5 .5 .1 .2 .9", False, "invalid"),
    ],
)
def test_empty_missing_and_invalid_predictions(environment, label, empty, expected):
    client, _, root = environment
    proj = project(client)
    (root / "inbox/spring_img.bmp").write_bytes(bmp_bytes())
    if label is not None:
        (root / "inbox/spring_img.txt").write_text(label, encoding="utf-8")
    result = submit(client, proj, options(proj, empty))[0]
    if expected == "invalid":
        assert result["outcome"] == "invalid"
        assert client.get(f"/api/v1/projects/{proj['id']}/images").json()["items"] == []
    else:
        assert result["label_state"] == expected


def test_existing_unlabeled_image_and_active_lease(environment):
    client, _, root = environment
    proj = project(client)
    (root / "inbox/spring_img.bmp").write_bytes(bmp_bytes())
    image = submit(client, proj, None)[0]
    (root / "inbox/spring_img.txt").write_text("0 .5 .5 .1 .2", encoding="utf-8")
    lease = claim(client, image["image_id"])
    result = submit(client, proj, options(proj))[0]
    assert result["code"] == "CLAIMED_BY_OTHER" and result["image_retained"]
    client.delete(f"/api/v1/images/{image['image_id']}/claim", headers=lease)
    assert submit(client, proj, options(proj))[0]["revision"] == 1


def test_ambiguous_pairs_and_mapping_rejected(environment):
    client, _, root = environment
    proj = project(client)
    (root / "inbox/spring_img.bmp").write_bytes(bmp_bytes())
    (root / "inbox/spring_img.png").write_bytes(b"other image with same stem")
    assert submit(client, proj, options(proj))[0]["code"] == "AMBIGUOUS_PAIR"
    invalid = options(proj)
    invalid["class_mapping"] = {"0": uid()}
    response = client.post(
        f"/api/v1/projects/{proj['id']}/imports",
        json={"relative_paths": ["spring_img.bmp"], "yolo": invalid},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 422


def test_invalid_bmp_header_rejected():
    with pytest.raises(Problem):
        image_header(b"BM" + bytes(40))


@pytest.mark.parametrize("bits", [8, 32])
def test_bmp_indexed_and_32_bit_decode(tmp_path, bits):
    palette = bytes((0, 0, 255, 0, 255, 0, 0, 0)) if bits == 8 else b""
    pixels = bytes((0, 1, 0, 0)) if bits == 8 else bytes((0, 0, 255, 0, 255, 0, 0, 0))
    offset = 54 + len(palette)
    raw = (
        struct.pack("<2sIHHI", b"BM", offset + len(pixels), 0, 0, offset)
        + struct.pack("<IiiHHIIiiII", 40, 2, 1, 1, bits, 0, len(pixels), 2835, 2835, 2 if bits == 8 else 0, 0)
        + palette
        + pixels
    )
    path = tmp_path / "fixture.bmp"
    path.write_bytes(raw)
    w, h, rgba, ext = decode(path)
    assert (w, h, ext) == (2, 1, "bmp")
    assert rgba[:3] == bytes((255, 0, 0)) and rgba[4:7] == bytes((0, 0, 255))


def test_case_insensitive_unicode_subfolder_pair(environment):
    client, _, root = environment
    proj = project(client)
    folder = root / "inbox/ชุดงาน"
    folder.mkdir()
    (folder / "Spring.BMP").write_bytes(bmp_bytes())
    (folder / "Spring.TXT").write_text("0 .5 .5 .2 .2", encoding="utf-8")
    result = submit(client, proj, options(proj), ["ชุดงาน/Spring.BMP"])[0]
    assert result["revision"] == 1 and result["shape_count"] == 1


def test_prediction_import_rejects_classification_project(environment):
    client, _, _ = environment
    proj = project(client, "classification")
    response = client.post(
        f"/api/v1/projects/{proj['id']}/imports",
        json={"relative_paths": ["spring_img.bmp"], "yolo": options(proj)},
        headers={"Idempotency-Key": uid()},
    )
    assert response.status_code == 422 and response.json()["error"]["code"] == "INVALID_TASK"

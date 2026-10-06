import io
import json
import subprocess
import sys
import threading
import time
import zipfile

import pytest
from conftest import claim, import_files, project, save_body

from visionlabel.domain import Problem, digest, uid
from visionlabel.working_export import install_archive, split_items


def labeled(client, root, task="detection", count=10):
    proj = project(client, task)
    images = import_files(client, root, proj["id"], count)
    for image in images:
        body = save_body(proj)
        if task == "classification":
            body["content"]["shapes"] = []
            body["content"]["image_labels"] = [proj["schema"]["entries"][0]["class_id"]]
        if task == "segmentation":
            body["content"]["shapes"] = [
                {
                    "id": uid(),
                    "type": "polygon",
                    "class_id": proj["schema"]["entries"][0]["class_id"],
                    "points": [[10, 20], [50, 20], [50, 100]],
                    "attributes": {},
                }
            ]
        lease = claim(client, image["id"])
        response = client.put(
            f"/api/v1/images/{image['id']}/annotation",
            json=body,
            headers=lease | {"Idempotency-Key": uid()},
        )
        assert response.status_code == 200, response.text
        assert client.delete(f"/api/v1/images/{image['id']}/claim", headers=lease).status_code == 204
    return proj, images


def start(client, proj, **body):
    return client.post(
        f"/api/v1/projects/{proj['id']}/working-exports", json=body, headers={"Idempotency-Key": uid()}
    )


def wait(client, job_id):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["state"] in ("succeeded", "failed"):
            return job
        time.sleep(0.01)
    pytest.fail("Export did not finish")


@pytest.mark.parametrize("task", ["detection", "segmentation", "classification"])
def test_real_dataset_archive_and_local_publication(environment, tmp_path, task):
    client, srv, root = environment
    proj, images = labeled(client, root, task)
    response = start(client, proj)
    assert response.status_code == 202, response.text
    job_id = response.json()["job_id"]
    job = wait(client, job_id)
    assert job["state"] == "succeeded", job
    assert job["result"]["split"]["actual_counts"] == {"train": 7, "val": 2, "test": 1}
    response = client.get(f"/api/v1/working-exports/{job_id}/download")
    assert response.status_code == 200, response.text
    raw = response.content
    assert digest(raw) == job["result"]["sha256"]
    bundle = zipfile.ZipFile(io.BytesIO(raw))
    manifest = json.loads(bundle.read("manifest.json"))
    assert manifest["approved_release"] is False
    assert len(manifest["items"]) == len(images)
    assert not manifest["excluded"]
    for item in manifest["items"]:
        assert digest(bundle.read(item["image_path"])) == item["asset_sha256"]
        assert item["current_revision"] == 1
        if task != "classification":
            text = bundle.read(f"labels/{item['partition']}/{item['image_id']}.txt").decode()
            values = text.split()
            assert values[0] == "0"
            if task == "detection":
                assert list(map(float, values[1:])) == [0.3, 0.3, 0.4, 0.4]
            else:
                points = list(zip(map(float, values[1::2]), map(float, values[2::2]), strict=True))
                assert set(points) == {(0.1, 0.1), (0.5, 0.1), (0.5, 0.5)}
        else:
            assert item["image_path"].startswith(item["partition"] + "/0000_class_0/")
    archive = tmp_path / "dataset.zip"
    archive.write_bytes(raw)
    destination = tmp_path / "ชุดข้อมูล"
    install_archive(archive, destination, job["result"]["sha256"])
    assert (destination / "TRAINING.txt").is_file()
    if task != "classification":
        assert json.dumps(destination.as_posix(), ensure_ascii=False) in (
            destination / "data.local.yaml"
        ).read_text(encoding="utf-8")
        moved = tmp_path / "moved dataset"
        destination.rename(moved)
        subprocess.run([sys.executable, str(moved / "prepare_dataset.py")], cwd=tmp_path, check=True)
        assert json.dumps(moved.as_posix(), ensure_ascii=False) in (moved / "data.local.yaml").read_text(
            encoding="utf-8"
        )
        moved.rename(destination)
    with pytest.raises(Problem, match="existing folders"):
        install_archive(archive, destination, job["result"]["sha256"])
    again = wait(client, start(client, proj).json()["job_id"])
    assert again["result"]["sha256"] == job["result"]["sha256"]


def test_excluded_and_verified_empty(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=4)
    with srv.db.engine.connect() as conn:
        image = (
            conn.exec_driver_sql("SELECT * FROM annotation_heads WHERE image_id=?", (images[0]["id"],))
            .mappings()
            .one()
        )
    body = save_body(proj, image["current_revision"], image["state_revision"])
    body["content"] = {"verified_empty": True, "shapes": [], "image_labels": []}
    headers = claim(client, images[0]["id"])
    assert (
        client.put(
            f"/api/v1/images/{images[0]['id']}/annotation",
            json=body,
            headers=headers | {"Idempotency-Key": uid()},
        ).status_code
        == 200
    )
    # An additional unique unlabeled image (not a duplicate of the first four).
    from visionlabel.fixtures import png_bytes

    (root / "inbox/unlabeled.png").write_bytes(png_bytes(100, 100, 200))
    from test_prediction_import import submit

    submit(client, proj, None, paths=["unlabeled.png"])
    job_id = start(client, proj, test_percent=0).json()["job_id"]
    job = wait(client, job_id)
    assert job["state"] == "succeeded", job
    assert job["result"]["excluded_count"] == 1
    bundle = zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/working-exports/{job_id}/download").content))
    assert any(
        bundle.read(n) == b"" for n in bundle.namelist() if n.endswith(".txt") and n.startswith("labels/")
    )
    assert not any("/test/" in n for n in bundle.namelist())


@pytest.mark.parametrize(
    "body",
    [
        {"validation_percent": 0},
        {"validation_percent": 90, "test_percent": 10},
        {"test_percent": -1},
        {"validation_percent": 20.5},
    ],
)
def test_invalid_percentages(environment, body):
    client, _, _ = environment
    assert start(client, project(client), **body).status_code == 422


def test_snapshot_is_frozen_while_working_heads_change(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=4)
    gate = threading.Event()
    blocker = srv.pool.submit(gate.wait, 10)
    try:
        job_id = start(client, proj, test_percent=0).json()["job_id"]
        body = save_body(proj, 1, 1)
        body["content"]["shapes"][0]["x2"] = 70
        reply = client.put(
            f"/api/v1/images/{images[0]['id']}/annotation",
            json=body,
            headers=claim(client, images[0]["id"]) | {"Idempotency-Key": uid()},
        )
        assert reply.status_code == 200, reply.text
    finally:
        gate.set()
        blocker.result()
    job = wait(client, job_id)
    assert job["state"] == "succeeded", job
    bundle = zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/working-exports/{job_id}/download").content))
    manifest = json.loads(bundle.read("manifest.json"))
    assert all(i["current_revision"] == 1 for i in manifest["items"])
    assert all(
        b"0.400000000 0.400000000" in bundle.read(n)
        for n in bundle.namelist()
        if n.startswith("labels/") and n.endswith(".txt")
    )


def test_corrupt_asset_and_publication_failure_leave_no_download(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=4)

    def failure(point):
        if point == "export_before_publish":
            raise OSError("Synthetic disk failure")

    srv.fault = failure
    job_id = start(client, proj, test_percent=0).json()["job_id"]
    assert wait(client, job_id)["state"] == "failed"
    assert not (root / "export-cache" / f"{job_id}.zip").exists()
    srv.fault = lambda _: None
    with srv.db.engine.connect() as conn:
        path = conn.exec_driver_sql(
            "SELECT blob_path FROM assets WHERE sha256=?", (images[0]["asset_sha256"],)
        ).scalar()
    (root / "managed" / path).write_bytes(b"corrupt")
    job_id = start(client, proj, test_percent=0).json()["job_id"]
    assert wait(client, job_id)["error"]["code"] == "CORRUPT_BLOB"


def test_group_boundaries_determinism_and_infeasibility():
    items = [
        {
            "image_id": f"image-{i}",
            "asset_sha256": str(i),
            "group_key": str(i // 2),
            "class_ids": ["A"],
            "verified_empty": False,
        }
        for i in range(12)
    ]
    options = {"validation_percent": 20, "test_percent": 10, "seed": 42}
    first, report = split_items(items, options)
    assert first == split_items(list(reversed(items)), options)[0]
    for i in range(0, 12, 2):
        assert first[f"image-{i}"] == first[f"image-{i + 1}"]
    assert sum(report["actual_counts"].values()) == 12
    with pytest.raises(Problem):
        split_items(items[:2], options)


def test_reject_unlisted_archive_path(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("manifest.json", json.dumps({"profile": "working-yolo-export-1", "files": []}))
        bundle.writestr("../escaped.txt", "bad")
    with pytest.raises(Problem):
        install_archive(path, tmp_path / "output", digest(path.read_bytes()))
    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "output").exists()


def test_permissions_idempotency_and_download_revocation(environment):
    from test_team import create_user, member

    client, srv, root = environment
    proj, _ = labeled(client, root, count=4)
    junior = create_user(client)
    assert member(client, proj, junior, "annotator").status_code == 200
    admin_auth = client.headers["Authorization"]
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    assert start(client, proj).status_code == 403
    client.headers["Authorization"] = admin_auth
    assert member(client, proj, junior, "maintainer", 2).status_code == 200
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]
    headers = {"Idempotency-Key": uid()}
    url = f"/api/v1/projects/{proj['id']}/working-exports"
    response = client.post(url, json={"test_percent": 0}, headers=headers)
    assert response.status_code == 202
    assert client.post(url, json={"test_percent": 0}, headers=headers).json() == response.json()
    assert client.post(url, json={"test_percent": 10}, headers=headers).status_code == 409
    job_id = response.json()["job_id"]
    assert wait(client, job_id)["state"] == "succeeded"
    assert client.get(f"/api/v1/working-exports/{job_id}/download").status_code == 200
    junior_auth = client.headers["Authorization"]
    client.headers["Authorization"] = admin_auth
    assert member(client, proj, junior, "viewer", 3).status_code == 200
    client.headers["Authorization"] = junior_auth
    assert client.get(f"/api/v1/working-exports/{job_id}/download").status_code == 403


def test_permission_rechecked_at_publication(environment):
    from test_team import create_user, member

    client, srv, root = environment
    proj, _ = labeled(client, root, count=4)
    junior = create_user(client)
    assert member(client, proj, junior, "maintainer").status_code == 200
    admin_auth = client.headers["Authorization"]
    client.headers["Authorization"] = "Bearer " + srv.login("junior", "a-long-user-password")["token"]

    def revoke(point):
        if point == "export_before_publish":
            with srv.db.transaction() as conn:
                conn.exec_driver_sql(
                    "UPDATE project_members SET role='viewer' WHERE project_id=? AND user_id=?",
                    (proj["id"], junior["id"]),
                )

    srv.fault = revoke
    job_id = start(client, proj, test_percent=0).json()["job_id"]
    client.headers["Authorization"] = admin_auth
    assert wait(client, job_id)["error"]["code"] == "FORBIDDEN"
    assert not (root / "export-cache" / f"{job_id}.zip").exists()


def test_client_verifies_each_file_and_rejects_listed_traversal(tmp_path):
    for index, (name, expected_hash) in enumerate(
        [("../outside.txt", digest(b"payload")), ("file.txt", digest(b"wrong"))]
    ):
        path = tmp_path / f"bad-{index}.zip"
        with zipfile.ZipFile(path, "w") as bundle:
            bundle.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "profile": "working-yolo-export-1",
                        "files": [{"path": name, "bytes": 7, "sha256": expected_hash}],
                    }
                ),
            )
            bundle.writestr(name, b"payload")
        with pytest.raises(Problem):
            install_archive(path, tmp_path / f"out-{index}", digest(path.read_bytes()))
        assert not (tmp_path / f"out-{index}").exists()
    assert not (tmp_path / "outside.txt").exists()

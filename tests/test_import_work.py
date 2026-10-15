import os
import subprocess
import sys
import threading

import pytest
from conftest import project

from visionlabel.domain import Problem, uid
from visionlabel.fixtures import bmp_bytes, png_bytes
from visionlabel.imaging import decode
from visionlabel.import_work import PairIndex
from visionlabel.service import Service


def test_pair_index_reuses_directory_and_rebuilds_after_change(tmp_path):
    source = tmp_path / "ภาพ.PNG"
    source.write_bytes(b"fixture")
    index = PairIndex()
    index.check(source)
    index.check(source)
    assert index.scans == 1
    (tmp_path / "ภาพ.jpg").write_bytes(b"duplicate stem")
    stamp = tmp_path.stat().st_mtime_ns
    os.utime(tmp_path, ns=(stamp, stamp + 1000000))
    with pytest.raises(Problem, match="Multiple images"):
        index.check(source)
    assert index.scans == 2


def test_validation_still_decodes_raster_without_returning_pixel_copy(tmp_path):
    source = tmp_path / "sample.bmp"
    source.write_bytes(bmp_bytes(5, 3))
    assert decode(source, pixels_required=False) == (5, 3, b"", "bmp")
    assert len(decode(source)[2]) == 5 * 3 * 4
    source.write_bytes(source.read_bytes()[:60])
    with pytest.raises(Problem):
        decode(source, pixels_required=False)


def test_progress_rows_are_durable_and_compact_poll_omits_running_report(environment):
    client, srv, root = environment
    proj = project(client)
    for i in range(3):
        (root / "inbox" / f"{i}.png").write_bytes(png_bytes(i, 10, 10))
    reached, release = threading.Event(), threading.Event()

    def fault(point):
        if point == "after_import_result":
            reached.set()
            assert release.wait(15)

    srv.fault = fault
    try:
        reply = client.post(
            f"/api/v1/projects/{proj['id']}/imports",
            json={"relative_paths": [f"{i}.png" for i in range(3)]},
            headers={"Idempotency-Key": uid()},
        )
        assert reply.status_code == 202
        jid = reply.json()["job_id"]
        assert reached.wait(15)
        compact = client.get(f"/api/v1/jobs/{jid}?compact=true").json()
        full = client.get(f"/api/v1/jobs/{jid}").json()
        assert compact["progress"]["done"] == 1 and compact["result"] is None
        assert full["result"]["items"][0]["path"] == "0.png"
        with srv.db.engine.connect() as conn:
            assert conn.exec_driver_sql("SELECT result_json FROM jobs WHERE id=?", (jid,)).scalar() is None
            assert (
                conn.exec_driver_sql("SELECT COUNT(*) FROM import_results WHERE job_id=?", (jid,)).scalar()
                == 1
            )
    finally:
        release.set()
        srv.pool.submit(lambda: None).result(timeout=20)
    terminal = client.get(f"/api/v1/jobs/{jid}?compact=true").json()
    assert terminal["state"] == "succeeded"
    assert len(terminal["result"]["items"]) == 3
    assert terminal["result"]["performance"]["stage_seconds"]["progress_commit"] >= 0


def test_decoder_start_failure_finishes_job(environment, monkeypatch):
    client, srv, root = environment
    proj = project(client)
    monkeypatch.setattr(
        "visionlabel.service.DecoderSession", lambda: (_ for _ in ()).throw(OSError("failed"))
    )
    reply = client.post(
        f"/api/v1/projects/{proj['id']}/imports",
        json={"relative_paths": ["unused.png"]},
        headers={"Idempotency-Key": uid()},
    )
    srv.pool.submit(lambda: None).result(timeout=10)
    job = client.get(f"/api/v1/jobs/{reply.json()['job_id']}").json()
    assert job["state"] == "failed" and job["result"]["items"] == []


def test_import_reuses_scratch_and_truncates_shorter_image(environment, monkeypatch):
    from test_prediction_import import submit

    from visionlabel.imaging import DecoderSession

    client, srv, root = environment
    proj = project(client)
    (root / "inbox/large.bmp").write_bytes(bmp_bytes(200, 200))
    (root / "inbox/small.bmp").write_bytes(bmp_bytes(10, 10))
    seen = []
    original = DecoderSession.inspect

    def inspect(decoder, path):
        seen.append((path, path.stat().st_size))
        return original(decoder, path)

    monkeypatch.setattr(DecoderSession, "inspect", inspect)
    result = submit(client, proj, None, ["large.bmp", "small.bmp"])
    srv.pool.submit(lambda: None).result(timeout=10)
    assert all(i["outcome"] == "imported" for i in result)
    assert seen[0][0] == seen[1][0]
    assert seen[1][1] == len(bmp_bytes(10, 10)) < seen[0][1]
    assert not seen[0][0].parent.exists()


def test_new_ambiguous_sibling_during_decode_is_rejected(environment, monkeypatch):
    from test_prediction_import import options, submit

    from visionlabel.imaging import DecoderSession

    client, srv, root = environment
    proj = project(client)
    source = root / "inbox/spring_img.bmp"
    source.write_bytes(bmp_bytes())
    (root / "inbox/spring_img.txt").write_text("0 0.5 0.5 0.25 0.25\n")
    original = DecoderSession.inspect

    def inspect(decoder, path):
        result = original(decoder, path)
        (root / "inbox/SPRING_IMG.png").write_bytes(png_bytes(0, 10, 10))
        stamp = source.parent.stat().st_mtime_ns
        os.utime(source.parent, ns=(stamp, stamp + 1000000))
        return result

    monkeypatch.setattr(DecoderSession, "inspect", inspect)
    result = submit(client, proj, options(proj))
    assert result[0]["code"] == "AMBIGUOUS_PAIR"
    assert client.get(f"/api/v1/projects/{proj['id']}/images").json()["items"] == []


@pytest.mark.parametrize("mode", ["inbox", "yolo"])
def test_import_report_survives_abrupt_process_exit(environment, tmp_path, mode):
    client, srv, root = environment
    proj = project(client)
    for i in range(2):
        (root / "inbox" / f"crash-{i}.png").write_bytes(png_bytes(i, 10, 10))
        (root / "inbox" / f"crash-{i}.txt").write_text("0 0.5 0.5 0.25 0.25\n")
    srv.close()
    code = """
import os,sys,time
from pathlib import Path
from visionlabel.service import Service
from visionlabel.domain import uid
s=Service(Path(sys.argv[1]))
u=s.authenticate(s.login('admin','a-strong-test-password')['token'])
body={'relative_paths':['crash-0.png','crash-1.png'],'dry_run':False}
boundary='after_import_result'
if sys.argv[3]=='yolo':
    p=s.project(u,sys.argv[2])
    body['yolo']={'class_schema_id':p['active_schema_id'],'class_mapping':{'0':p['schema']['entries'][0]['class_id']},'empty_is_verified':False}
    boundary='after_commit'
s.fault=lambda point: os._exit(73) if point==boundary else None
s.import_images(u,sys.argv[2],body,uid(),uid())
time.sleep(20)
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(root), proj["id"], mode],
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    restarted = Service(root)
    client.app.state.service = restarted
    assert result.returncode == 73
    with restarted.db.engine.connect() as conn:
        jid = conn.exec_driver_sql("SELECT id FROM jobs WHERE type='import'").scalar()
    job = client.get(f"/api/v1/jobs/{jid}?compact=true").json()
    assert job["state"] == "failed" and job["progress"]["done"] == 1
    assert job["result"]["items"][0]["path"] == "crash-0.png"
    iid = job["result"]["items"][0]["image_id"]
    assert client.get(f"/api/v1/images/{iid}/content").status_code == 200


def test_prediction_commit_failure_rolls_back_success_report(environment):
    from test_prediction_import import options, submit

    client, srv, root = environment
    proj = project(client)
    (root / "inbox/spring_img.bmp").write_bytes(bmp_bytes())
    (root / "inbox/spring_img.txt").write_text("0 0.5 0.5 0.25 0.25\n")

    def fail(point):
        if point == "before_commit":
            raise Problem("SIMULATED_FAILURE", "Commit failed.", 503)

    srv.fault = fail
    result = submit(client, proj, options(proj))[0]
    assert result["outcome"] == "invalid" and result["code"] == "SIMULATED_FAILURE"
    assert result["image_retained"]
    head = client.get(f"/api/v1/images/{result['image_id']}/annotation").json()
    assert head["revision"] == 0 and head["annotation"] is None

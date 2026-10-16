import io
import json
import threading
import zipfile
from types import SimpleNamespace

import httpx
import pytest

from visionlabel.client import Client
from visionlabel.domain import Problem, digest
from visionlabel.working_export import PROFILE, install_archive


def dataset_archive(wrong_file_hash=False):
    data = b"image bytes" * 100_000
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as bundle:
        bundle.writestr("train/part/image.bmp", data)
        bundle.writestr(
            "manifest.json",
            json.dumps(
                {
                    "profile": PROFILE,
                    "task_type": "classification",
                    "files": [
                        {
                            "path": "train/part/image.bmp",
                            "bytes": len(data),
                            "sha256": "0" * 64 if wrong_file_hash else digest(data),
                        }
                    ],
                }
            ),
        )
    return output.getvalue(), data


@pytest.mark.parametrize("failure", [None, "archive_hash", "file_hash", "size", "disconnect"])
def test_download_checks_stream_and_members_before_publication(tmp_path, monkeypatch, failure):
    from visionlabel import working_export

    raw, expected_image = dataset_archive(failure == "file_hash")
    destination = tmp_path / "dataset"
    progress = []

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            for offset in range(0, len(raw), 131072):
                if failure == "disconnect" and offset:
                    raise httpx.ReadError("Disconnected")
                yield raw[offset : offset + 131072]

    client = Client()
    client.http.close()
    client.http = httpx.Client(
        base_url="http://127.0.0.1/api/v1",
        transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=Stream())),
    )
    # The client hashes while downloading/extracting, never rereading completed files.
    monkeypatch.setattr(working_export, "file_hash", lambda *args: pytest.fail("Unexpected disk reread"))
    result = {
        "bytes": len(raw) + (1 if failure == "size" else 0),
        "sha256": "0" * 64 if failure == "archive_hash" else digest(raw),
    }
    try:
        if failure:
            with pytest.raises(Problem):
                client.download_export("job", destination, result, lambda *event: progress.append(event))
            assert not destination.exists()
            assert list(tmp_path.iterdir()) == []
        else:
            client.download_export("job", destination, result, lambda *event: progress.append(event))
            assert (destination / "train/part/image.bmp").read_bytes() == expected_image
            assert {p[0] for p in progress} >= {
                "Downloading and verifying archive",
                "Extracting and verifying files",
                "Finalizing dataset folder",
            }
            byte_steps = [p for p in progress if p[0] == "Downloading and verifying archive"]
            assert byte_steps[-1][1:3] == (len(raw), len(raw))
    finally:
        client.close()


def test_direct_archive_install_still_verifies_full_checksum(tmp_path):
    raw, _ = dataset_archive()
    archive = tmp_path / "input.zip"
    archive.write_bytes(raw)
    with pytest.raises(Problem, match="checksum"):
        install_archive(archive, tmp_path / "dataset", "0" * 64)
    assert not (tmp_path / "dataset").exists()


def test_progress_writes_are_bounded_and_phase_changes_visible(monkeypatch):
    from contextlib import contextmanager

    from visionlabel import export_progress

    clock, writes = [0.0], []
    monkeypatch.setattr(export_progress, "time", SimpleNamespace(monotonic=lambda: clock[0]))

    @contextmanager
    def transaction():
        yield SimpleNamespace(exec_driver_sql=lambda *args: writes.append(args))

    reporter = export_progress.JobProgress(
        SimpleNamespace(db=SimpleNamespace(transaction=transaction)), "job"
    )
    for count in range(5400):
        reporter("Building dataset archive", count, 5400)
    assert len(writes) == 1
    clock[0] = 0.6
    reporter("Building dataset archive", 5400, 5400)
    reporter("Verifying dataset archive", 0, 1_000_000, "bytes")
    assert len(writes) == 3
    assert json.loads(writes[-1][1][2])["progress"]["unit"] == "bytes"


def test_ui_workers_never_touch_widgets_and_late_progress_is_ignored(monkeypatch):
    from visionlabel import export_ui

    values, configs = {}, {}
    main_thread = threading.get_ident()

    def set_value(tag, value):
        assert threading.get_ident() == main_thread
        values[tag] = value

    monkeypatch.setattr(export_ui.dpg, "set_value", set_value)
    monkeypatch.setattr(export_ui.dpg, "configure_item", lambda tag, **kw: configs.update({tag: kw}))
    panel = export_ui.ExportPanel(SimpleNamespace())
    update = panel.begin_progress("save", "Starting")
    worker = threading.Thread(target=lambda: [update("Downloading", n, 5400) for n in range(2701)])
    worker.start()
    worker.join()
    assert values["export_save_progress"] == 0
    panel.tick_progress(force=True)
    assert values["export_save_progress"] == 0.5
    panel.finish_progress(True)
    update("Downloading", 1, 5400)
    panel.tick_progress(force=True)
    assert values["export_save_progress"] == 1.0
    assert configs["export_save_progress"]["overlay"] == "Complete"


def test_prepare_reads_reviews_once_and_converts_labels_once(environment, monkeypatch):
    from sqlalchemy import event
    from test_working_export import labeled, start, wait

    from visionlabel import working_export

    client, srv, root = environment
    project, _ = labeled(client, root, count=3)
    statements, conversions = [], []
    original = working_export.yolo_labels

    def convert(*args, **kwargs):
        conversions.append(kwargs["image_id"])
        return original(*args, **kwargs)

    def record(conn, cursor, statement, parameters, context, executemany):
        if "FROM working_reviews" in statement:
            statements.append(statement)

    monkeypatch.setattr(working_export, "yolo_labels", convert)
    event.listen(srv.db.engine, "before_cursor_execute", record)
    try:
        job = wait(client, start(client, project).json()["job_id"])
        assert job["state"] == "succeeded", job
        assert len(statements) == 1
        assert len(conversions) == len(set(conversions)) == 3
        assert job["progress"] == {"done": 1, "total": 1, "phase": "Complete", "unit": "steps"}
        assert "Building dataset archive" in job["result"]["performance"]["stage_seconds"]
    finally:
        event.remove(srv.db.engine, "before_cursor_execute", record)


def test_running_progress_does_not_become_failed_history_result(environment, monkeypatch):
    from test_working_export import labeled, start, wait

    from visionlabel import working_export
    from visionlabel.project_ui import version_report

    client, srv, root = environment
    project, _ = labeled(client, root, count=3)
    observations = []

    def fail_split(*args):
        with srv.db.engine.connect() as conn:
            job_id = conn.exec_driver_sql("SELECT id FROM jobs WHERE type='working-export'").scalar_one()
        running = client.get(f"/api/v1/jobs/{job_id}?compact=true").json()
        observations.append(running)
        raise Problem("TEST_FAILURE", "Synthetic split failure")

    monkeypatch.setattr(working_export, "split_items", fail_split)
    job = wait(client, start(client, project).json()["job_id"])
    assert observations[0]["progress"]["phase"] == "Assigning dataset splits"
    assert observations[0]["result"] is None
    assert job["state"] == "failed" and job["result"] is None
    history = client.get(f"/api/v1/projects/{project['id']}/versions").json()
    assert "Synthetic split failure" in version_report(history)

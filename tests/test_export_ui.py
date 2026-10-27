import json
from types import SimpleNamespace

import pytest

from visionlabel.domain import Problem
from visionlabel.export_ui import ExportPanel, failure_report


@pytest.fixture(autouse=True)
def headless_visibility(monkeypatch):
    from visionlabel import export_ui

    # These tests use a fake widget model, not a native Dear PyGui context.
    monkeypatch.setattr(export_ui.dpg, "hide_item", lambda _: None)
    monkeypatch.setattr(export_ui.dpg, "show_item", lambda _: None)
    monkeypatch.setattr(export_ui.dpg, "does_item_exist", lambda _: True)


def test_failed_job_details_reach_desktop_and_local_report(monkeypatch, tmp_path):
    from visionlabel import export_ui

    issue = {
        "filename": "ภาพ.png",
        "image_id": "image-1",
        "annotation_revision": 4,
        "width": 3,
        "height": 3,
        "shape_number": 2,
        "shape_id": "shape-1",
        "export_index": 0,
        "class_name": "part",
        "failed_checks": ["LEFT_OUT_OF_BOUNDS"],
        "edges": {"left": "-0.0000000005"},
    }
    error = {"code": "UNREPRESENTABLE_GEOMETRY", "message": "Export blocked.", "details": {"issues": [issue]}}
    calls = []

    def request(method, path, *args, **kwargs):
        calls.append((method, path, kwargs.get("key")))
        return {"job_id": "job-1"} if method == "POST" else {"state": "failed", "error": error}

    def submit(work, done, failed):
        try:
            done(work())
        except Problem as exc:
            failed(exc)

    values = {
        "export_val": 20,
        "export_test": 10,
        "export_seed": 42,
        "export_parent": str(tmp_path),
        "export_report_format": "JSON",
        "export_mapping": "",
    }
    configs = {}
    monkeypatch.setattr(export_ui.dpg, "get_value", values.__getitem__)
    monkeypatch.setattr(export_ui.dpg, "set_value", values.__setitem__)
    monkeypatch.setattr(
        export_ui.dpg, "configure_item", lambda tag, **kw: configs.setdefault(tag, {}).update(kw)
    )
    app = SimpleNamespace(
        project={"id": "project", "schema": {"entries": []}},
        client=SimpleNamespace(request=request),
        exit_requested=False,
        submit=submit,
    )
    panel = ExportPanel(app)
    panel.project_id = "project"
    panel.prepare()
    assert "ภาพ.png" in values["export_report"]
    assert "shape-1" in values["export_report"]
    assert "-0.0000000005" in values["export_report"]
    assert not configs["export_save"]["enabled"]
    assert configs["export_save_report"]["enabled"]
    assert panel.request_key is None
    panel.save_error_report()
    panel.save_error_report()
    reports = list(tmp_path.glob("export-errors-*.json"))
    assert len(reports) == 2  # Each save creates a new file.
    assert json.loads(reports[0].read_text(encoding="utf-8"))["details"] == {
        "issues": [issue],
        "job_id": "job-1",
    }
    panel.prepare()
    assert calls[0][2] != calls[2][2]  # Retry requests a new frozen snapshot.


def test_old_job_without_details_remains_readable():
    assert failure_report(Problem("EXPORT_FAILED", "Old error")) == "Old error"


def test_prepare_locks_class_mapping_until_response(monkeypatch):
    from visionlabel import export_ui

    values = {"export_mapping": "", "export_val": 20, "export_test": 10, "export_seed": 42}
    configs, pending = {}, []
    monkeypatch.setattr(export_ui.dpg, "get_value", values.__getitem__)
    monkeypatch.setattr(export_ui.dpg, "set_value", values.__setitem__)
    monkeypatch.setattr(
        export_ui.dpg, "configure_item", lambda tag, **kw: configs.setdefault(tag, {}).update(kw)
    )
    panel = ExportPanel(
        SimpleNamespace(
            project={"id": "project", "schema": {"entries": []}},
            client=object(),
            submit=lambda *callbacks: pending.append(callbacks),
            exit_requested=False,
        )
    )
    panel.project_id = "project"
    panel.prepare()
    assert len(pending) == 1 and panel.busy
    assert configs["export_mapping"]["enabled"] is False
    pending[0][2](Problem("DISCONNECTED", "Try again", 503))
    assert not panel.busy and configs["export_mapping"]["enabled"] is True
    assert configs["export_save"]["enabled"] is False


def test_review_warning_cancel_and_confirm_bind_exact_candidate(monkeypatch):
    from visionlabel import export_ui

    values = {"export_mapping": "", "export_val": 20, "export_test": 0, "export_seed": 42}
    monkeypatch.setattr(export_ui.dpg, "get_value", values.__getitem__)
    monkeypatch.setattr(export_ui.dpg, "set_value", values.__setitem__)
    monkeypatch.setattr(export_ui.dpg, "configure_item", lambda *a, **k: None)
    calls = []
    candidate = "11111111-1111-4111-8111-111111111111"

    def request(method, path, body=None, **kwargs):
        if method == "POST":
            calls.append(body)
            if not body["confirmation"]:
                raise Problem(
                    "REVIEW_CONFIRMATION_REQUIRED",
                    "Review is incomplete.",
                    409,
                    confirmation=candidate,
                    counts={"IN_PROGRESS": 3},
                    captured_at="2026-10-10T00:00:00Z",
                    snapshot_sha256="source",
                )
            return {"job_id": "job"}
        return {"state": "failed", "error": {"code": "INVALID_GEOMETRY", "message": "Inspect labels."}}

    def submit(work, done, failed):
        try:
            done(work())
        except Problem as exc:
            failed(exc)

    panel = ExportPanel(
        SimpleNamespace(
            project={"id": "project", "schema": {"entries": []}},
            client=SimpleNamespace(request=request),
            exit_requested=False,
            submit=submit,
        )
    )
    panel.project_id = "project"
    panel.prepare()
    assert len(calls) == 1 and panel.review_confirmation == candidate
    panel.cancel_review()
    assert len(calls) == 1 and panel.review_confirmation is None
    panel.prepare()
    panel.confirm_review()
    assert len(calls) == 3 and calls[-1]["confirmation"] == candidate
    assert calls[-1]["validation_percent"] == calls[0]["validation_percent"]
    assert panel.review_confirmation is None


@pytest.mark.parametrize(
    "changed,exists,blocked,lease",
    [
        (False, True, False, True),
        (True, True, False, True),
        (True, False, False, True),
        (False, True, True, True),
        (False, True, False, False),
    ],
)
def test_open_issue_uses_navigation_guard_and_loaded_identity(monkeypatch, changed, exists, blocked, lease):
    from visionlabel import export_ui

    frames, actions, messages, selected = [], [], [], []
    monkeypatch.setattr(export_ui.dpg, "get_value", lambda _: 1)
    monkeypatch.setattr(export_ui.dpg, "hide_item", lambda _: None)
    monkeypatch.setattr(export_ui.dpg, "get_frame_count", lambda: 5)
    monkeypatch.setattr(export_ui.dpg, "set_frame_callback", lambda frame, callback: frames.append(callback))
    app = SimpleNamespace(
        client=object(),
        project={"id": "project"},
        guard=actions.append,
        head={"revision": 2 if changed else 1, "annotation_sha256": "new" if changed else "old"},
        editor=SimpleNamespace(content={"shapes": [{"id": "shape"}] if exists else []}),
        blocked=blocked,
        claim=lease,
        message=messages.append,
        select_shape=selected.append,
    )
    opened = []

    def open_image(image_id, on_loaded):
        opened.append(image_id)
        on_loaded()

    app.open_image = open_image
    panel = ExportPanel(app)
    panel.project_id = "project"
    panel.report_client = app.client
    panel.failed_report = {
        "details": {
            "issues": [
                {
                    "image_id": "image",
                    "shape_id": "shape",
                    "annotation_revision": 1,
                    "annotation_sha256": "old",
                }
            ]
        }
    }
    panel.open_issue()
    assert not opened
    frames[0]()
    assert not opened  # Save/keep/cancel navigation belongs to Desktop.guard.
    actions[0]()
    assert opened == ["image"]
    assert selected == (["shape"] if exists and not blocked else [])
    assert ("changed since" in messages[0]) == changed
    assert ("no longer exists" in messages[0]) == (not exists and not blocked)
    assert ("recovery draft" in messages[0]) == blocked
    assert ("Read-only" in messages[0]) == (not lease)


def test_csv_preserves_exact_values_and_escapes_spreadsheet_formulas(monkeypatch, tmp_path):
    import csv

    from visionlabel import export_ui

    values = {"export_parent": str(tmp_path), "export_report_format": "CSV"}
    monkeypatch.setattr(export_ui.dpg, "get_value", values.__getitem__)
    monkeypatch.setattr(export_ui.dpg, "set_value", values.__setitem__)
    panel = ExportPanel(None)
    panel.failed_report = {
        "details": {
            "job_id": "job",
            "issues": [
                {"filename": "=danger.png", "class_name": "ชิ้นงาน", "edges": {"left": "-0.0000000005"}}
            ],
        }
    }
    panel.save_error_report()
    with next(tmp_path.glob("*.csv")).open(encoding="utf-8-sig", newline="") as stream:
        row = next(csv.DictReader(stream))
    assert row["filename"] == "'=danger.png"
    assert row["class_name"] == "ชิ้นงาน"
    assert json.loads(row["edges"])["left"] == "-0.0000000005"

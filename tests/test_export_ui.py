import json
from types import SimpleNamespace

import pytest

from visionlabel.domain import Problem
from visionlabel.export_ui import ExportPanel, failure_report


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
        project={"schema": {"entries": []}},
        client=SimpleNamespace(request=request),
        exit_requested=False,
        submit=submit,
    )
    panel = ExportPanel(app)
    panel.project_id = "project-1"
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

"""Observable guard outcomes, routing and preservation at user-action boundaries."""

from concurrent.futures import Future
from queue import Queue
from types import SimpleNamespace

import pytest

from visionlabel import feedback
from visionlabel.canvas import Canvas
from visionlabel.desktop import Desktop
from visionlabel.domain import Editor, Problem
from visionlabel.export_ui import ExportPanel
from visionlabel.project_ui import ProjectPanel
from visionlabel.review_ui import ReviewPanel
from visionlabel.team_ui import TeamPanel


@pytest.fixture
def ui(monkeypatch):
    values, shown, configs = {}, set(), {}
    dpg = feedback.dpg
    monkeypatch.setattr(dpg, "set_value", values.__setitem__)
    monkeypatch.setattr(dpg, "get_value", lambda tag: values.get(tag, ""))
    monkeypatch.setattr(dpg, "does_item_exist", lambda tag: True)
    monkeypatch.setattr(dpg, "is_item_shown", lambda tag: tag in shown)
    monkeypatch.setattr(dpg, "show_item", shown.add)
    monkeypatch.setattr(dpg, "hide_item", shown.discard)
    monkeypatch.setattr(dpg, "configure_item", lambda tag, **kw: configs.setdefault(tag, {}).update(kw))
    return values, shown, configs


def desktop():
    app = Desktop.__new__(Desktop)
    app.image = app.head = app.project = app.claim = app.store = None
    app.busy = app.saving = app.blocked = app.navigation_save = False
    app.next_action = app.pending_save = None
    app.client = SimpleNamespace(user=None)
    app.editor = Editor()
    app.canvas = Canvas(app.editor)
    app.review = ReviewPanel(app)
    app.project_manager = ProjectPanel(app)
    app.exports = ExportPanel(app)
    app.render = lambda: None
    return app


def test_connection_and_create_failures_stay_in_current_dialog(ui):
    values, shown, _ = ui
    app = desktop()
    shown.add("connection")
    app.busy = True
    app.connect()
    assert "Wait" in values["connection_status"]
    shown.clear()
    shown.add("new_project")
    app.create_project()
    assert "running" in values["new_project_status"]
    app.busy = False
    app.create_project()
    assert "not connected" in values["new_project_status"]


def test_async_result_retains_owner_when_another_modal_opens(ui):
    values, shown, _ = ui
    app = desktop()
    future = Future()
    app.pool = SimpleNamespace(submit=lambda work: future)
    app.completed = Queue()
    shown.add("connection")
    app.submit(lambda: None, lambda _: app.message("Connection result"))
    shown.clear()
    shown.add("new_project")
    future.set_result(None)
    callback, value, _ = app.completed.get_nowait()
    callback(value)
    assert values["connection_status"] == "Connection result"
    assert "new_project_status" not in values


def test_explicit_save_and_background_noop_have_different_feedback(ui):
    values, _, _ = ui
    app = desktop()
    app.save(background=True)
    assert not values
    app.save()
    assert "No image" in values["status"] and "Open" in values["status"]
    app.image = {"id": "one"}
    app.project, app.head, app.store = {}, {}, object()
    app.claim = {"mode": "edit"}
    app.save()
    assert "No changes to save" in values["status"]


def test_failed_recovery_write_keeps_navigation_and_dialog(ui):
    values, shown, _ = ui
    app = desktop()
    proceeded = []
    app.next_action = lambda: proceeded.append(True)
    app.persist_draft = lambda: (_ for _ in ()).throw(OSError("disk full"))
    shown.add("dirty_dialog")
    app.keep_then_continue()
    assert not proceeded and app.next_action is not None
    assert "dirty_dialog" in shown
    assert "free space" in values["dirty_status"]
    assert "preserved" not in values["dirty_status"]


def test_review_invalid_reason_is_local_and_does_not_dispatch(ui):
    values, shown, _ = ui
    app = desktop()
    app.guard = lambda _: pytest.fail("invalid reason dispatched")
    values.update(review_reason="Other", review_comment=" ")
    shown.add("review_reject")
    app.review.reject()
    assert "Other requires a reason" in values["review_reject_status"]
    assert "review_reject" in shown


@pytest.mark.parametrize(
    ("state", "expected"),
    [("role", "role cannot review"), ("busy", "Wait"), ("status", "not IN_PROGRESS"), ("blocked", "Resolve")],
)
def test_review_eligibility_and_request_use_same_reason(ui, state, expected):
    values, _, _ = ui
    app = desktop()
    app.project = {"can_review": state != "role"}
    app.head = {"status": "UNLABELED" if state == "status" else "IN_PROGRESS"}
    app.busy = state == "busy"
    app.blocked = state == "blocked"
    assert not app.review.eligible()
    app.review.request("accept")
    assert values["status"] == app.review.unavailable_reason()
    assert expected in values["status"]


@pytest.mark.parametrize(
    "method",
    ["prepare", "apply", "compare", "resume_preview", "usage", "find_pending", "view_image", "export"],
)
def test_dataset_busy_actions_explain_in_current_browser(ui, method):
    values, shown, _ = ui
    app = desktop()
    panel = app.project_manager.datasets
    app.project_manager.busy = True
    shown.add("checkpoint_browser")
    getattr(panel, method)("checkpoint") if method == "prepare" else getattr(panel, method)()
    assert "Wait" in values["ds_browser_status"]


def test_checkpoint_progress_does_not_erase_cancellation_feedback(ui):
    values, _, _ = ui
    app = desktop()
    panel = app.project_manager.datasets
    app.project_manager.busy = True
    panel.message("Cancellation failed. Inspect the operation result.")
    panel.progress_text = "Verifying: 12/20"
    panel.tick()
    assert values["ds_status"].startswith("Cancellation failed")
    assert values["ds_progress"] == "Verifying: 12/20"


def test_export_confirmation_survives_busy_and_invalid_input(ui):
    values, _, _ = ui
    app = desktop()
    app.project = {"id": "project", "schema": {"entries": []}}
    panel = app.exports
    panel.project_id = "project"
    panel.review_confirmation = "candidate"
    panel.busy = True
    panel.confirm_review()
    assert panel.review_confirmation == "candidate"
    panel.busy = False
    values.update(export_mapping="", export_val=100, export_test=10, export_seed=42)
    panel.confirm_review()
    assert panel.review_confirmation == "candidate"
    assert "percentages" in values["export_status"]


def test_export_prevents_cross_project_dispatch(ui):
    values, _, _ = ui
    app = desktop()
    app.project = {"id": "new"}
    panel = app.exports
    panel.project_id = "old"
    app.submit = lambda *a: pytest.fail("cross-project export dispatched")
    panel.prepare()
    assert "project changed" in values["export_status"]


@pytest.mark.parametrize(
    "method",
    [
        "save_project",
        "open_selected",
        "save_template",
        "load_versions",
        "load_images",
        "preview_remap",
        "apply_remap",
    ],
)
def test_project_selection_guards_are_observable(ui, method):
    values, _, _ = ui
    panel = desktop().project_manager
    getattr(panel, method)()
    assert "No project" in values["pm_status"] and "Select" in values["pm_status"]


def test_team_no_selection_and_retry_are_explained(ui):
    values, _, _ = ui
    panel = TeamPanel(desktop())
    panel.use_user()
    assert "No account" in values["team_status"]
    panel.retry()
    assert "No request" in values["team_status"]


def test_busy_shortcut_explains_but_typing_still_suppresses(ui, monkeypatch):
    values, _, _ = ui
    app = desktop()
    app.modal_open = lambda: False
    app.review_keys = set()
    app.text_inputs = ["search"]
    app.busy = True
    monkeypatch.setattr(feedback.dpg, "is_key_down", lambda key: key == feedback.dpg.mvKey_LControl)
    monkeypatch.setattr(feedback.dpg, "is_item_active", lambda tag: False)
    app.key_press(None, feedback.dpg.mvKey_S)
    assert "Wait" in values["status"]
    values.clear()
    monkeypatch.setattr(feedback.dpg, "is_item_active", lambda tag: True)
    app.key_press(None, feedback.dpg.mvKey_S)
    assert not values


def test_transport_failure_never_claims_rollback_or_draft_preservation():
    text = feedback.failure_text(
        Problem("DISCONNECTED", "Connection lost.", 503), "Inspect the operation result."
    )
    assert "unknown" in text and "Inspect" in text
    assert "preserved" not in text and "unchanged" not in text

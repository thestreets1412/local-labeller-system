import copy
from types import SimpleNamespace

import pytest

from visionlabel import desktop as module
from visionlabel.canvas import Canvas
from visionlabel.desktop import Desktop
from visionlabel.domain import Editor, Problem
from visionlabel.image_delete_ui import ImageDeletePanel
from visionlabel.review_ui import ReviewPanel


@pytest.fixture
def app(monkeypatch):
    ui = {"autosave": True, "filter": "All", "search": ""}
    shown = []
    for name in ("configure_item", "hide_item"):
        monkeypatch.setattr(module.dpg, name, lambda *a, **k: None)
    monkeypatch.setattr(module.dpg, "get_value", lambda tag: ui.get(tag))
    monkeypatch.setattr(module.dpg, "set_value", lambda tag, value: ui.__setitem__(tag, value))
    monkeypatch.setattr(module.dpg, "show_item", shown.append)
    instance = Desktop.__new__(Desktop)
    instance.editor = Editor()
    instance.canvas = Canvas(instance.editor)
    instance.busy = instance.saving = instance.blocked = instance.navigation_save = False
    instance.next_action = instance.pending_save = None
    instance.pending_load_claim = None
    instance.image_query_generation = 0
    instance.review = SimpleNamespace(busy=False, refresh=lambda: None)
    instance.project = {"id": "project", "active_schema_id": "schema"}
    instance.image = {"id": "one", "status": "IN_PROGRESS"}
    instance.images = [instance.image, {"id": "two"}, {"id": "three"}]
    instance.head = {"revision": 1, "state_revision": 1, "status": "IN_PROGRESS"}
    instance.claim = {"mode": "edit"}
    instance.store = SimpleNamespace(remove_draft=lambda _: None)
    instance.message = lambda message: ui.__setitem__("status", message)
    instance.error = lambda error: ui.__setitem__("error", error)
    instance.render = instance.populate_images = instance.persist_draft = lambda: None
    calls, requests, opened = [], [], []
    instance.client = SimpleNamespace(request=lambda *args, **kwargs: requests.append((args, kwargs)))
    instance.submit = lambda work, success, failure: calls.append((work, success, failure))
    instance.open_image = opened.append
    instance.editor.change({"shapes": [], "image_labels": ["class"], "verified_empty": False})
    return instance, ui, shown, calls, requests, opened


def acknowledge(instance, callback):
    callback(
        {
            "revision": instance.head["revision"] + 1,
            "state_revision": instance.head["state_revision"] + 1,
            "annotation_sha256": "hash",
            "status": "IN_PROGRESS",
        }
    )


def test_image_deletion_cancel_keeps_edits_and_transport_retry_keeps_key(app):
    instance, ui, shown, calls, requests, _ = app
    instance.project["can_manage_members"] = True
    instance.image["display_filename"] = "sample.png"
    panel = ImageDeletePanel(instance)
    panel.request()
    assert instance.busy and shown[-1] == "delete_image_dialog"
    panel.cancel()
    assert instance.editor.dirty and not instance.busy and not calls
    panel.request()
    first = panel.pending.copy()
    panel.confirm()
    panel.confirm()
    assert len(calls) == 1
    calls[0][2](Problem("DISCONNECTED", "Connection lost.", 503))
    assert instance.editor.dirty and not instance.busy
    panel.request()
    assert panel.pending["key"] == first["key"]
    panel.confirm()
    calls[-1][0]()
    assert requests[-1][1]["key"] == first["key"]


def test_image_deletion_requires_maintainer_and_ignores_busy_state(app):
    instance, ui, shown, calls, _, _ = app
    panel = ImageDeletePanel(instance)
    panel.request()
    assert not shown and not calls and "Maintainer" in ui["status"]
    instance.project["can_manage_members"] = True
    instance.saving = True
    panel.request()
    assert not shown and panel.pending is None


def test_autosave_navigation_waits_and_first_destination_wins(app):
    instance, ui, shown, calls, _, opened = app
    instance.navigate(1)
    assert instance.saving and not shown and not opened
    instance.guard(lambda: opened.append("three"))
    assert len(calls) == 1
    acknowledge(instance, calls[0][1])
    assert opened == ["two"] and not instance.editor.dirty
    assert not instance.navigation_save and instance.next_action is None


def test_navigation_attaches_to_inflight_save_and_flushes_newer_content(app):
    instance, _, shown, calls, _, opened = app
    instance.save()
    latest = copy.deepcopy(instance.editor.content)
    latest["image_labels"] = ["another class"]
    instance.editor.change(latest)
    instance.navigate(1)
    assert len(calls) == 1 and not shown
    acknowledge(instance, calls[0][1])
    assert len(calls) == 2 and not opened
    acknowledge(instance, calls[1][1])
    assert opened == ["two"] and not instance.editor.dirty


@pytest.mark.parametrize("status", [403, 409, 422])
def test_save_failure_keeps_image_and_draft(app, status):
    instance, _, _, calls, _, opened = app
    instance.navigate(1)
    calls[0][2](Problem("FAILED", "Save failed", status))
    assert not opened and instance.editor.dirty and instance.image["id"] == "one"
    assert instance.next_action is None and not instance.navigation_save


def test_lost_acknowledgement_reuses_save_key(app):
    instance, _, _, calls, requests, opened = app
    instance.navigate(1)
    calls[0][0]()
    calls[0][2](Problem("DISCONNECTED", "Retry", 503))
    instance.save()
    calls[1][0]()
    assert requests[0][1]["key"] == requests[1][1]["key"]
    acknowledge(instance, calls[1][1])
    assert opened == ["two"]


def test_autosave_off_and_active_gesture(app):
    instance, ui, shown, calls, _, opened = app
    ui["autosave"] = False
    instance.navigate(1)
    assert shown == ["dirty_dialog"] and not calls and not opened
    instance.cancel_navigation()
    instance.canvas.gesture = {"kind": "draw"}
    instance.navigate(1)
    assert not calls and instance.next_action is None


@pytest.mark.parametrize("blocked,claim", [(True, {"mode": "edit"}), (False, None)])
def test_blocked_navigation_offers_draft_preserving_recovery(app, blocked, claim):
    instance, _, shown, calls, _, opened = app
    instance.blocked, instance.claim = blocked, claim
    drafts = []
    instance.persist_draft = lambda: drafts.append(copy.deepcopy(instance.editor.content))
    instance.guard(lambda: opened.append("reload"))
    assert shown == ["dirty_dialog"] and not calls and not opened
    instance.keep_then_continue()
    assert opened == ["reload"] and drafts == [instance.editor.content]


@pytest.mark.parametrize("operation", ["class", "delete"])
def test_rectangle_commands_during_drag_survive_mouse_release(app, operation):
    instance, _, _, _, _, _ = app
    instance.can_edit = lambda: True
    instance.populate_classes = instance.edited = lambda: None
    instance.project["task_type"] = "detection"
    instance.editor.load(
        {
            "verified_empty": False,
            "image_labels": [],
            "shapes": [
                {
                    "id": "shape",
                    "type": "rectangle",
                    "class_id": "old",
                    "attributes": {},
                    "x1": 10,
                    "y1": 10,
                    "x2": 30,
                    "y2": 30,
                }
            ],
        }
    )
    instance.canvas.width = instance.canvas.height = 100
    instance.canvas.mode = "select"
    instance.canvas.start(20, 20, "old")
    instance.canvas.move(25, 25)
    if operation == "class":
        instance.select_class("new")
    else:
        instance.delete_selected()
    instance.canvas.finish()
    if operation == "class":
        assert instance.editor.content["shapes"][0]["class_id"] == "new"
    else:
        assert instance.editor.content["shapes"] == []


@pytest.mark.parametrize("failure_path", ["annotation", "reviews", "decode", "draft"])
def test_failed_image_load_releases_acquired_claim(app, failure_path):
    instance, _, _, calls, _, _ = app
    instance.claim = None
    instance.project["can_edit"] = True
    requests = []

    def fail():
        raise Problem("DISCONNECTED", "Load failed", 503)

    def request(method, path, *args, **kwargs):
        requests.append((method, path, kwargs))
        if path.endswith("/" + failure_path):
            fail()
        if method == "POST":
            return {"claim_id": "lease", "mode": "edit"}
        if method == "DELETE":
            return None
        if path.endswith("/annotation"):
            return {}
        if path.endswith("/reviews"):
            return {"items": []}
        return {"id": "two", "project_id": "project", "status": "IN_PROGRESS"}

    instance.client = SimpleNamespace(request=request, instance="client")
    instance.store = SimpleNamespace(
        read_cached=lambda _: b"pixels",
        decode_image=lambda *args: fail() if failure_path == "decode" else (1, 1, b"\0" * 4, "png"),
        load_draft=lambda _: fail() if failure_path == "draft" else None,
    )
    Desktop.open_image(instance, "two")
    work, _, failed = calls.pop()
    with pytest.raises(Problem) as error:
        work()
    failed(error.value)
    assert instance.claim is None
    releases = [r for r in requests if r[0] == "DELETE"]
    assert len(releases) == 1 and releases[0][1] == "/images/two/claim"
    assert releases[0][2]["claim"]["claim_id"] == "lease"


@pytest.mark.parametrize("lost_ack", [False, True])
def test_load_retry_recovers_claim_after_cleanup_disconnect(app, lost_ack):
    instance, _, _, calls, _, _ = app
    instance.claim = None
    instance.project["can_edit"] = True
    posts, releases = [], []
    online = False

    def request(method, path, *args, **kwargs):
        if method == "POST":
            posts.append(kwargs["key"])
            if lost_ack and not online:
                raise Problem("DISCONNECTED", "Acknowledgement lost", 503)
            return {"claim_id": "lease", "mode": "edit"}
        if method == "DELETE":
            releases.append(kwargs["claim"])
            if not online:
                raise Problem("DISCONNECTED", "Cleanup unavailable", 503)
            return None
        if path.endswith("/annotation"):
            raise Problem("DISCONNECTED", "Annotation unavailable", 503)
        return {"id": "two", "project_id": "project", "status": "IN_PROGRESS"}

    instance.client = SimpleNamespace(request=request, instance="client")
    for attempt in range(2):
        online = bool(attempt)
        Desktop.open_image(instance, "two")
        work, _, failed = calls.pop()
        with pytest.raises(Problem) as error:
            work()
        failed(error.value)
        if attempt == 0:
            assert instance.pending_load_claim is not None
    assert instance.pending_load_claim is None
    assert posts[0] != posts[-1]  # A fresh claim only after recovery/release.
    if lost_ack:
        assert posts[:3] == [posts[0]] * 3
    assert releases[-1]["claim_id"] == "lease"


def test_title_uses_project_order_not_filtered_queue(app, monkeypatch):
    instance, ui, _, _, _, _ = app
    panel = ReviewPanel(instance)
    panel.overview = {
        "total": 5000,
        "image_ids": [str(i) for i in range(5000)],
        "counts": {"IN_PROGRESS": 840},
    }
    instance.image = {"id": "1249"}
    instance.images = [{"id": "1249"}, {"id": "4000"}]
    titles = []
    monkeypatch.setattr(module.dpg, "set_viewport_title", titles.append)
    panel.position()
    assert titles == ["VisionLabel - Annotation workspace: [1250/5000]"]
    assert ui["image_count"] == "Queue: 1/2 | Project: 1250/5000"


def test_review_hotkeys_ignore_text_modifiers_and_repeats(app, monkeypatch):
    instance, _, _, _, _, _ = app
    calls = []
    instance.review = SimpleNamespace(request=calls.append)
    instance.review_keys = set()
    instance.text_inputs = ["comment"]
    instance.modal_open = lambda: False
    monkeypatch.setattr(module.dpg, "is_item_active", lambda _: True)
    monkeypatch.setattr(module.dpg, "is_key_down", lambda _: False)
    instance.key_press(None, module.dpg.mvKey_S)
    assert not calls
    monkeypatch.setattr(module.dpg, "is_item_active", lambda _: False)
    instance.review_keys.clear()  # release after typing, then a fresh key press
    instance.key_press(None, module.dpg.mvKey_S)
    instance.key_press(None, module.dpg.mvKey_S)
    assert calls == ["accept"]
    instance.review_keys.clear()
    monkeypatch.setattr(module.dpg, "is_key_down", lambda key: key == module.dpg.mvKey_LShift)
    instance.key_press(None, module.dpg.mvKey_X)
    assert calls == ["accept"]

"""Checkpoint and class tools; all durable changes go through DataTracking."""

import json
import time
from typing import Any

import dearpygui.dearpygui as dpg

from .domain import Problem, uid
from .feedback import BUSY, PROJECT, failure_text
from .texture import rgba_texture


def preview_report(result):
    diff = result["diff"]
    lines = [
        f"{result['kind'].title()}: {result['label']}",
        result["message"],
        f"Captured images: {result['images']}",
        "Captured review states: " + ", ".join(f"{k}: {v}" for k, v in result["review_counts"].items()),
        f"Images added: {len(diff['added_images'])}; removed: {len(diff['removed_images'])}",
        f"Annotations changed: {len(diff['changed_annotations'])}; review-only changes: {len(diff['review_only'])}",
        "Class schema changes: " + ("Yes" if diff["schema_changed"] else "No"),
    ]
    if result["requires_new_review"]:
        lines += [
            "All restored/migrated saved annotations require fresh review.",
            "A safety checkpoint preserves the current saved dataset. Earlier checkpoints stay available.",
        ]
    else:
        lines.append("This captures saved data without changing the working project.")
    lines.append("Preview expires: " + result["expires_at"])
    return "\n".join(lines)


class DatasetPanel:
    def __init__(self, manager):
        self.manager = manager
        self.app = manager.app
        self.project: Any = None
        self.checkpoints = {}
        self.next_before = None
        self.preview: Any = None
        self.preview_key = None
        self.preview_body = None
        self.apply_key = None
        self.class_rows = []
        self.images = {}
        self.next_offset = None
        self.viewing: Any = None
        self.texture = None
        self.pending_release = None
        self.pending_operations = {}
        self.comparisons = {"Working data": None}
        self.progress_text = None

    def build(self):
        with dpg.window(
            tag="dataset_manager",
            label="Dataset checkpoints and classes",
            show=False,
            width=1000,
            height=760,
            pos=(100, 35),
            modal=True,
        ):
            dpg.add_text("", tag="ds_status", wrap=930)
            dpg.add_text("", tag="ds_progress", wrap=930)
            dpg.add_text(
                "Apply unavailable until a preview is ready. Prepare and inspect a preview first.",
                tag="ds_availability",
                wrap=930,
            )
            with dpg.child_window(tag="dataset_manager_feedback_body", width=-1, height=-1, border=False):
                dpg.add_text("", tag="ds_project")
                dpg.add_text(
                    "Working checkpoints are not approved releases. All changes use saved server data."
                )
                with dpg.tab_bar():
                    with dpg.tab(label="Checkpoints"):
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="Refresh", callback=lambda: self.refresh())
                            dpg.add_button(label="Older", callback=lambda: self.refresh(True))
                        dpg.add_listbox([], tag="ds_checkpoints", width=930, num_items=7)
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="Inspect images", callback=lambda: self.inspect())
                            dpg.add_button(label="Compare with", callback=lambda: self.compare())
                            dpg.add_combo(
                                ["Working data"], default_value="Working data", tag="ds_compare", width=200
                            )
                            dpg.add_button(label="Export checkpoint", callback=lambda: self.export())
                        dpg.add_button(
                            label="Preview restore to working data", callback=lambda: self.prepare("restore")
                        )
                        dpg.add_button(
                            label="Preview new checkpoint", callback=lambda: self.prepare("checkpoint")
                        )
                        with dpg.group(horizontal=True):
                            dpg.add_button(label="Find saved previews", callback=lambda: self.find_pending())
                            dpg.add_combo([], tag="ds_pending", width=500)
                            dpg.add_button(label="Resume preview", callback=lambda: self.resume_preview())
                    with dpg.tab(label="Edit classes"):
                        dpg.add_text(
                            "Rename or deactivate classes. Map/remove labels explicitly. All saved heads require review again.",
                            wrap=920,
                        )
                        dpg.add_text(
                            "Active | Name | Annotation action (Keep, Remove, or existing destination class)"
                        )
                        with dpg.child_window(tag="ds_classes", height=235):
                            pass
                        dpg.add_button(label="Add class", callback=lambda: self.add_class())
                        dpg.add_button(label="Refresh class usage", callback=lambda: self.usage())
                        dpg.add_input_text(
                            tag="ds_usage", multiline=True, readonly=True, width=920, height=60
                        )
                        dpg.add_button(label="Preview class changes", callback=lambda: self.prepare("schema"))
                dpg.add_input_text(label="Version label", tag="ds_label", width=400, callback=self.invalidate)
                dpg.add_input_text(label="Message", tag="ds_message", width=800, callback=self.invalidate)
                dpg.add_input_text(tag="ds_report", multiline=True, readonly=True, width=940, height=160)
                with dpg.group(horizontal=True):
                    dpg.add_button(
                        label="Apply preview / retry",
                        tag="ds_apply",
                        enabled=False,
                        callback=lambda: self.apply(),
                    )
                    dpg.add_button(label="Cancel preview / operation", callback=lambda: self.cancel())
                    dpg.add_button(label="Close", callback=lambda: dpg.hide_item("dataset_manager"))
        with dpg.window(
            tag="checkpoint_browser",
            on_close=self.close_browser,
            label="Checkpoint images (read-only)",
            width=920,
            height=780,
            show=False,
            modal=True,
        ):
            dpg.add_text("", tag="ds_browser_status", wrap=880)
            with dpg.child_window(tag="checkpoint_browser_feedback_body", width=-1, height=-1, border=False):
                dpg.add_text("", tag="ds_browser_title")
                dpg.add_listbox([], tag="ds_images", width=880, num_items=4)
                with dpg.group(horizontal=True):
                    dpg.add_button(label="View image and annotation", callback=lambda: self.view_image())
                    dpg.add_button(label="Next images", callback=lambda: self.inspect(next_page=True))
                    dpg.add_button(label="Close", callback=self.close_browser)
                dpg.add_drawlist(tag="ds_canvas", width=860, height=460)
                dpg.add_input_text(tag="ds_annotation", multiline=True, readonly=True, width=880, height=140)
        self.app.text_inputs.extend(["ds_label", "ds_message"])

    def close_browser(self):
        dpg.hide_item("checkpoint_browser")
        self.app.exports.show_after_modal_closes("dataset_manager")

    def message(self, value):
        target = "ds_browser_status" if dpg.is_item_shown("checkpoint_browser") else "ds_status"
        dpg.set_value(target, value)

    def ready(self):
        if self.manager.busy or self.app.busy or self.app.saving or self.app.review.busy:
            self.message(BUSY)
            return False
        if not self.project:
            self.message(PROJECT)
            return False
        return True

    def tick(self):
        if self.manager.busy and self.progress_text:
            dpg.set_value("ds_progress", self.progress_text)

    def run(self, work, done):
        if not self.ready():
            return
        owner = "ds_browser_status" if dpg.is_item_shown("checkpoint_browser") else "ds_status"
        self.manager.busy = self.app.busy = True
        client = self.app.client
        controls = ["ds_label", "ds_message"] + [
            tag for _, active, name, action, _ in self.class_rows for tag in (active, name, action)
        ]
        for tag in controls:
            dpg.configure_item(tag, enabled=False)

        def finish():
            self.manager.busy = self.app.busy = False
            self.progress_text = None
            dpg.set_value("ds_progress", "")
            for tag in controls:
                if dpg.does_item_exist(tag):
                    dpg.configure_item(tag, enabled=True)

        def completed(value):
            finish()
            if client is self.app.client:
                done(value)

        def failed(exc):
            finish()
            if client is self.app.client:
                dpg.set_value(
                    owner,
                    failure_text(
                        exc,
                        "Inspect the dataset and saved previews. Retry the same operation if its result is unknown; prepare a fresh preview if the dataset changed.",
                    ),
                )

        self.app.submit(work, completed, failed)

    def find_pending(self):
        if not self.ready():
            return
        pid, client = self.project["id"], self.app.client

        def done(result):
            self.pending_operations = {
                f"{r['label']} | {r['kind']} | {r['message']}": r for r in result["items"]
            }
            dpg.configure_item("ds_pending", items=list(self.pending_operations))
            dpg.set_value("ds_pending", next(iter(self.pending_operations), ""))
            self.message(
                "Saved previews expire after 24 hours. Select one to resume, or prepare a new preview."
                if self.pending_operations
                else "No saved previews were found. Prepare a new checkpoint, restore or class preview."
            )

        self.run(lambda: client.request("GET", f"/projects/{pid}/dataset-operations"), done)

    def resume_preview(self):
        if not self.ready():
            return
        preview = self.pending_operations.get(dpg.get_value("ds_pending"))
        if preview:
            self.preview = preview
            self.apply_key = uid()
            dpg.set_value("ds_label", preview["label"])
            dpg.set_value("ds_message", preview["message"])
            dpg.set_value("ds_report", preview_report(preview))
            dpg.configure_item("ds_apply", enabled=True)
            dpg.set_value("ds_availability", "Preview ready. Inspect its impact, then Apply or Cancel.")
        else:
            self.message("No saved preview is selected. Find saved previews, then select one to resume.")

    def cancel(self):
        if not self.preview:
            self.invalidate()
            self.message("No preview or operation is selected to cancel. Prepare or resume a preview first.")
            return
        self.message("Cancellation requested. Wait for the service to confirm the final state.")
        pid, ident, client = self.project["id"], self.preview["operation_id"], self.app.client

        def done(result):
            if result["cancelled"]:
                self.preview = None
                dpg.configure_item("ds_apply", enabled=False)
                self.message("Cancelled. Existing working data is unchanged.")
            else:
                self.message("Already committed. The saved checkpoint remains available.")

        # Cancellation can run while the operation worker is verifying blobs.
        self.app.submit(
            lambda: client.request("DELETE", f"/projects/{pid}/dataset-operations/{ident}"),
            done,
            lambda exc: self.message(
                failure_text(
                    exc,
                    "Inspect the saved preview and operation result before requesting cancellation again.",
                )
            ),
        )

    def usage(self):
        if not self.ready():
            return
        pid, client = self.project["id"], self.app.client
        self.run(
            lambda: client.request("GET", f"/projects/{pid}/class-usage"),
            lambda result: dpg.set_value(
                "ds_usage",
                "\n".join(
                    f"{r['name']}: {r['objects']} labels in {r['images']} images" for r in result["items"]
                ),
            ),
        )

    def invalidate(self, *args):
        if self.manager.busy:
            return
        self.preview = None
        self.preview_key = None
        self.preview_body = None
        self.apply_key = None
        dpg.configure_item("ds_apply", enabled=False)
        dpg.set_value(
            "ds_availability", "Apply unavailable: prepare a preview, inspect its impact, then Apply."
        )

    def open(self):
        if self.manager.busy or self.app.busy or self.app.saving or self.app.review.busy:
            self.manager.message(BUSY)
            return
        if not self.manager.selected:
            self.manager.message("Select a project in Project Manager first.")
            return
        self.project = self.manager.selected
        if not self.project.get("can_manage_members"):
            self.manager.message(
                "A project maintainer role is required to edit classes or dataset checkpoints. Ask a maintainer for access, then Refresh this project."
            )
            return
        self.comparisons = {"Working data": None}
        self.invalidate()
        dpg.set_value("ds_project", self.project["name"])
        dpg.set_value(
            "ds_report",
            "Create a preview, inspect its impact, then Apply. Restore/schema changes preserve a safety checkpoint.",
        )
        self.class_rows = []
        dpg.delete_item("ds_classes", children_only=True)
        for entry in self.project["schema"]["entries"]:
            self.add_class(entry)
        dpg.hide_item("project_manager")
        # Dear PyGui needs a rendered frame between hiding one modal and showing another.
        self.app.exports.show_after_modal_closes("dataset_manager")
        self.refresh()

    def add_class(self, entry=None):
        if not self.ready():
            return
        self.invalidate()
        destinations = {"Keep": "keep", "Remove": None}
        destinations.update(
            {f"Map to: {e['display_name']}": e["class_id"] for e in self.project["schema"]["entries"]}
        )
        with dpg.group(parent="ds_classes", horizontal=True):
            active = dpg.add_checkbox(
                default_value=bool(entry["active"]) if entry else True, callback=self.invalidate
            )
            name = dpg.add_input_text(
                default_value=entry["display_name"] if entry else "", width=300, callback=self.invalidate
            )
            action = dpg.add_combo(
                list(destinations), default_value="Keep", width=300, callback=self.invalidate
            )
        self.class_rows.append((entry["class_id"] if entry else None, active, name, action, destinations))

    def refresh(self, older=False):
        if not self.ready():
            return
        if older and not self.next_before:
            self.message(
                "There are no older checkpoints on this page. Choose a listed checkpoint or Refresh."
            )
            return
        pid, client = self.project["id"], self.app.client
        suffix = f"?before={self.next_before}" if older else ""

        def done(result):
            self.checkpoints = {
                f"{c['sequence']} | {'Safety checkpoint' if c['label'].startswith('__safety__') else c['label']} | {c['message']} | {c['created_at'][:19]} UTC | {c['author']}": c
                for c in result["items"]
            }
            dpg.configure_item("ds_checkpoints", items=list(self.checkpoints))
            dpg.set_value("ds_checkpoints", next(iter(self.checkpoints), ""))
            self.next_before = result["next_before"]
            self.comparisons.update({f"{c['sequence']}: {c['label']}": c["id"] for c in result["items"]})
            dpg.configure_item("ds_compare", items=list(self.comparisons))
            if dpg.get_value("ds_compare") not in self.comparisons:
                dpg.set_value("ds_compare", "Working data")
            self.message(
                "Choose a checkpoint or enter a new version label and message."
                if self.checkpoints
                else "No checkpoints were found. Enter a version label and message, then Preview new checkpoint."
            )

        self.run(lambda: client.request("GET", f"/projects/{pid}/checkpoints{suffix}"), done)

    def chosen(self):
        selected = self.checkpoints.get(dpg.get_value("ds_checkpoints"))
        if not selected:
            raise Problem("SELECT_CHECKPOINT", "Select a checkpoint first.")
        return selected

    def prepare(self, kind):
        if not self.ready():
            return
        if self.app.canvas.gesture or getattr(self.app.canvas, "draft", None):
            self.message(
                "An annotation is unfinished. Close this window, finish or cancel the drawing and save your edits before preparing a preview."
            )
            return
        if self.app.editor.dirty:
            self.message(
                "The current image has unsaved changes. Close this window and save the image, then return to prepare a preview."
            )
            return
        try:
            body = {"kind": kind, "label": dpg.get_value("ds_label"), "message": dpg.get_value("ds_message")}
            if kind == "restore":
                body["checkpoint_id"] = self.chosen()["id"]
            if kind == "schema":
                body["classes"], body["mapping"] = [], {}
                for ident, active, name, action, destinations in self.class_rows:
                    body["classes"].append(
                        {
                            "class_id": ident,
                            "display_name": dpg.get_value(name),
                            "active": dpg.get_value(active),
                        }
                    )
                    value = destinations[dpg.get_value(action)]
                    if ident and value != "keep":
                        body["mapping"][ident] = value
            pid, client = self.project["id"], self.app.client
            if self.preview_key is None or self.preview_body != body:
                self.preview_key, self.preview_body = uid(), body
            key = self.preview_key

            def done(result):
                self.preview = result
                self.apply_key = uid()
                dpg.set_value("ds_report", preview_report(result))
                dpg.configure_item("ds_apply", enabled=True)
                dpg.set_value("ds_availability", "Preview ready. Inspect its impact, then Apply or Cancel.")
                self.message(
                    "Preview ready. Apply uses these frozen inputs; other users' unsaved edits are not included."
                )

            self.run(lambda: client.request("POST", f"/projects/{pid}/dataset-preview", body, key=key), done)
        except Problem as exc:
            self.message(exc.message)

    def apply(self):
        if not self.ready():
            return
        if not self.preview:
            self.message("No preview is ready. Prepare and inspect a preview before applying it.")
            return
        if self.app.editor.dirty or self.app.saving:
            self.message(
                "The current image has unsaved changes. Close this window and save it, then prepare a fresh preview before applying."
            )
            return
        preview, pid, client = self.preview, self.project["id"], self.app.client
        key = self.apply_key
        current = self.app.image
        lease = self.app.claim if current and current.get("project_id") == pid else None
        if preview["kind"] != "checkpoint" and lease:
            self.pending_release = (client, current["id"], lease)
            self.app.claim = None
            self.app.blocked = True
        self.message(
            "Verifying files and applying dataset operation. Working data stays consistent throughout."
        )

        def work():
            if self.pending_release:
                release_client, release_id, release_claim = self.pending_release
                release_client.request("DELETE", f"/images/{release_id}/claim", claim=release_claim)
                self.pending_release = None
            job = client.request(
                "POST", f"/projects/{pid}/dataset-operations/{preview['operation_id']}/apply", key=key
            )
            while not self.app.exit_requested:
                state = client.request("GET", f"/jobs/{job['job_id']}")
                progress = state.get("progress", {})
                self.progress_text = f"{progress.get('phase', state['state'])}: {progress.get('done', 0)}/{progress.get('total', 0)}"
                if state["state"] in ("succeeded", "failed"):
                    return state
                time.sleep(0.1)
            raise Problem(
                "CLIENT_STOPPING",
                "Operation continues on the service; inspect checkpoints after reconnecting.",
            )

        def done(job):
            if preview["kind"] != "checkpoint" and lease:
                self.app.claim = None
                self.app.blocked = True
            if job["state"] == "failed":
                self.apply_key = uid()
                self.message(
                    job["error"]["message"]
                    + " Retry uses the saved preview; changed data requires a fresh preview."
                )
                return
            self.invalidate()
            saved = job["result"]["checkpoint"]
            dpg.set_value(
                "ds_report",
                f"Saved {saved['label']}\n{saved['message']}\nCreated: {saved['created_at']}\nEarlier checkpoints remain available.",
            )
            self.message("Checkpoint saved. Restore/schema changes require fresh review.")
            if preview["kind"] != "checkpoint":
                # Explicitly discard only clean local state and reload the new schema/heads.
                dpg.hide_item("dataset_manager")
                self.app.guard(lambda: self.app.load_project(pid))
            else:
                self.refresh()

        self.run(work, done)

    def inspect(self, next_page=False):
        if not self.ready():
            return
        try:
            chosen = self.viewing if next_page else self.chosen()
            if next_page and self.next_offset is None:
                self.message(
                    "There are no more checkpoint images. Select an image already listed or close the browser."
                )
                return
            self.viewing = chosen
            offset = self.next_offset if next_page else 0
            pid, client = self.project["id"], self.app.client

            def done(result):
                self.images = {
                    f"{r['display_filename']} | {r['status']} | {r['image_id']}": r for r in result["items"]
                }
                self.view_schema = result["schema"]
                self.next_offset = result["next_offset"]
                dpg.configure_item("ds_images", items=list(self.images))
                dpg.set_value("ds_images", next(iter(self.images), ""))
                dpg.set_value(
                    "ds_browser_title",
                    f"{chosen['label']} | {result['total']} images | {result['review_counts']}",
                )
                dpg.delete_item("ds_canvas", children_only=True)
                dpg.set_value(
                    "ds_annotation", "Choose an image. This browser never acquires an editing lease."
                )
                dpg.set_value(
                    "ds_browser_status",
                    "Select an image, then View image and annotation."
                    if self.images
                    else "This checkpoint has no images on this page. Close the browser and choose another checkpoint.",
                )
                if not dpg.is_item_shown("checkpoint_browser"):
                    dpg.hide_item("dataset_manager")
                    self.app.exports.show_after_modal_closes("checkpoint_browser")

            self.run(
                lambda: client.request("GET", f"/projects/{pid}/checkpoints/{chosen['id']}?offset={offset}"),
                done,
            )
        except Problem as exc:
            self.message(exc.message)

    def view_image(self):
        if not self.ready():
            return
        record = self.images.get(dpg.get_value("ds_images"))
        if not record:
            self.message(
                "No image is selected. Select an image in this browser, then choose View image and annotation."
            )
            return
        if not self.app.store:
            self.message(
                "The local image store is unavailable. Close this browser and reconnect before inspecting images."
            )
            return
        client = self.app.client
        path = f"/projects/{self.project['id']}/checkpoints/{self.viewing['id']}/images/{record['image_id']}"

        def work():
            result = client.request("GET", path)
            data = client.request("GET", path + "/content", raw=True)
            width, height, pixels, _ = self.app.store.decode_image(record, data)
            return result, width, height, rgba_texture(pixels)

        def done(value):
            result, width, height, pixels = value
            dpg.delete_item("ds_canvas", children_only=True)
            if self.texture:
                dpg.delete_item(self.texture)
            self.texture = dpg.add_static_texture(width, height, pixels, parent="textures")
            scale = min(850 / record["width"], 450 / record["height"])
            dpg.draw_image(
                self.texture, (0, 0), (record["width"] * scale, record["height"] * scale), parent="ds_canvas"
            )
            names = {e["class_id"]: e["display_name"] for e in self.view_schema["entries"]}
            doc = result["annotation"]
            for shape in doc["shapes"] if doc else []:
                color = (255, 190, 60, 255)
                if shape["type"] == "rectangle":
                    start = (shape["x1"] * scale, shape["y1"] * scale)
                    dpg.draw_rectangle(
                        start,
                        (shape["x2"] * scale, shape["y2"] * scale),
                        color=color,
                        thickness=2,
                        parent="ds_canvas",
                    )
                else:
                    points = [(x * scale, y * scale) for x, y in shape["points"]]
                    start = points[0]
                    dpg.draw_polyline(points, closed=True, color=color, thickness=2, parent="ds_canvas")
                dpg.draw_text(start, names[shape["class_id"]], color=color, size=16, parent="ds_canvas")
            labels = [names[c] for c in doc["image_labels"]] if doc else []
            dpg.set_value(
                "ds_annotation",
                "Image labels: "
                + ", ".join(labels)
                + "\n"
                + json.dumps(result, ensure_ascii=False, indent=2),
            )

        self.run(work, done)

    def compare(self):
        if not self.ready():
            return
        try:
            chosen, pid, client = self.chosen(), self.project["id"], self.app.client
            other = self.comparisons.get(dpg.get_value("ds_compare"))
            suffix = f"?other={other}" if other else ""
            self.run(
                lambda: client.request("GET", f"/projects/{pid}/checkpoints/{chosen['id']}/diff{suffix}"),
                lambda result: dpg.set_value("ds_report", json.dumps(result, ensure_ascii=False, indent=2)),
            )
        except Problem as exc:
            self.message(exc.message)

    def export(self):
        if not self.ready():
            return
        try:
            chosen = self.chosen()
            if not self.app.project or self.app.project["id"] != self.project["id"]:
                self.message(
                    "This checkpoint belongs to another workspace project. Close this window, open the project in Project Manager, then return to export its checkpoint."
                )
                return
            client, pid = self.app.client, self.project["id"]

            def done(result):
                if self.app.exports.open_checkpoint(chosen, result["schema"], show=False):
                    dpg.hide_item("dataset_manager")
                    self.app.exports.show_after_modal_closes("export_dialog")

            self.run(
                lambda: client.request("GET", f"/projects/{pid}/checkpoints/{chosen['id']}?limit=1"), done
            )
        except Problem as exc:
            self.message(exc.message)

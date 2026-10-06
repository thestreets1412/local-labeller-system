"""English-only Dear PyGui editor. Only the UI thread calls Dear PyGui."""

import argparse
import copy
import ctypes
import json
import os
import queue
import time
from array import array
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import dearpygui.dearpygui as dpg

from .canvas import Canvas
from .client import Client, LocalStore
from .domain import Editor, Problem, canonical, empty_content, uid
from .export_ui import ExportPanel
from .polygon_canvas import PolygonCanvas
from .statistics_ui import StatisticsPanel
from .team_ui import TeamPanel


class Desktop:
    def __init__(self, url):
        self.client = Client(url)
        self.editor = Editor()
        self.canvas = Canvas(self.editor)
        self.pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="visionlabel")
        self.completed: queue.Queue = queue.Queue()
        self.store: LocalStore | None = None
        self.projects = []
        self.project: dict[str, Any] | None = None
        self.images = []
        self.image: dict[str, Any] | None = None
        self.head: dict[str, Any] | None = None
        self.claim: dict[str, Any] | None = None
        self.class_id: str | None = None
        self.texture = None
        self.texture_number = 0
        self.busy = False
        self.saving = False
        self.pending_save = None
        self.blocked = False
        self.edit_time = 0.0
        self.last_content = canonical(self.editor.content)
        self.heartbeat_time = 0.0
        self.heartbeat_pending = False
        self.heartbeat_failures = 0
        self.job = None
        self.job_time = 0.0
        self.job_pending = False
        self.yolo_job = False
        self.yolo_schema_key = None
        self.next_action = None
        self.exit_requested = False
        self.recovery = None
        self.frame_count = 0
        self.crosshair_visible = False
        self.crosshair_cursor_owned = False
        self.cursor_api = ctypes.WinDLL("user32", use_last_error=True)
        self.cursor_api.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        self.cursor_api.LoadCursorW.restype = ctypes.c_void_p
        self.cursor_api.SetCursor.argtypes = [ctypes.c_void_p]
        self.cursor_api.SetCursor.restype = ctypes.c_void_p
        self.crosshair_cursor = self.cursor_api.LoadCursorW(None, 32515)
        self.arrow_cursor = self.cursor_api.LoadCursorW(None, 32512)
        self.status = "Connect to your local DataTracking service to start."
        self.team = TeamPanel(self)
        self.statistics = StatisticsPanel(self)
        self.exports = ExportPanel(self)
        self.text_inputs = [
            "server",
            "username",
            "password",
            "project_name",
            "project_slug",
            "project_classes",
            "search",
            "yolo_mapping",
        ]

    def submit(self, work, success, failure=None):
        future = self.pool.submit(work)

        def finished(result):
            try:
                self.completed.put((success, result.result(), False))
            except Exception as exc:
                self.completed.put((failure or self.error, exc, True))

        future.add_done_callback(finished)

    def message(self, text):
        self.status = text
        dpg.set_value("status", text)

    def error(self, exc):
        self.busy = False
        self.message(
            exc.message
            if isinstance(exc, Problem)
            else f"Operation failed: {type(exc).__name__}. Your draft is preserved."
        )

    def build(self):
        dpg.create_context()
        dpg.configure_app(manual_callback_management=True)
        # Use the font installed with Windows; do not redistribute OS font files.
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "tahoma.ttf"
        if font_path.is_file():
            with dpg.font_registry():
                with dpg.font(str(font_path), 18) as font:
                    pass  # Dear PyGui 2.3 loads glyph ranges automatically.
            dpg.bind_font(font)
        with dpg.theme() as theme:
            with dpg.theme_component(dpg.mvAll):
                dpg.add_theme_color(dpg.mvThemeCol_WindowBg, (19, 23, 30))
                dpg.add_theme_color(dpg.mvThemeCol_ChildBg, (23, 28, 36))
                dpg.add_theme_color(dpg.mvThemeCol_FrameBg, (34, 42, 54))
                dpg.add_theme_color(dpg.mvThemeCol_Button, (40, 62, 72))
                dpg.add_theme_color(dpg.mvThemeCol_ButtonHovered, (51, 99, 109))
                dpg.add_theme_color(dpg.mvThemeCol_Header, (42, 77, 88))
                dpg.add_theme_color(dpg.mvThemeCol_CheckMark, (76, 201, 166))
                dpg.add_theme_style(dpg.mvStyleVar_FrameRounding, 4)
                dpg.add_theme_style(dpg.mvStyleVar_WindowPadding, 12, 10)
                dpg.add_theme_style(dpg.mvStyleVar_ItemSpacing, 8, 7)
        dpg.bind_theme(theme)
        with dpg.texture_registry(tag="textures"):
            pass
        with dpg.window(tag="main", label="VisionLabel", no_close=True):
            with dpg.group(horizontal=True):
                dpg.add_text("VISIONLABEL", color=(76, 201, 166))
                dpg.add_text("/  Annotation workspace", color=(170, 182, 198))
                dpg.add_spacer(width=20)
                dpg.add_button(label="Connection", callback=lambda: self.show_connection())
                dpg.add_button(label="New project", callback=lambda: dpg.show_item("new_project"))
                dpg.add_button(label="Import inbox", callback=lambda: self.import_inbox())
                dpg.add_button(label="Import YOLO labels", callback=lambda: self.show_yolo_import())
                dpg.add_button(label="Reload / reconnect", callback=lambda: self.guard(self.reload))
                dpg.add_button(label="Team & users", callback=lambda: self.guard(self.team.open))
            dpg.add_separator()
            with dpg.group(horizontal=True, tag="workspace"):
                with dpg.child_window(width=240, tag="sidebar"):
                    dpg.add_text("PROJECT")
                    dpg.add_combo([], tag="projects", width=-1, callback=self.select_project)
                    dpg.add_separator()
                    dpg.add_input_text(
                        tag="search",
                        hint="Search filename",
                        width=-1,
                        on_enter=True,
                        callback=lambda: self.refresh_images(),
                    )
                    dpg.add_combo(
                        ["All", "UNLABELED", "IN_PROGRESS"],
                        default_value="All",
                        tag="filter",
                        width=-1,
                        callback=lambda: self.refresh_images(),
                    )
                    dpg.add_text("No images", tag="image_count", color=(160, 173, 190))
                    with dpg.child_window(tag="image_list", height=-1, border=False):
                        pass
                with dpg.child_window(tag="center", width=-270):
                    with dpg.group(horizontal=True):
                        dpg.add_button(
                            label="Rectangle [R]",
                            tag="rectangle_tool",
                            callback=lambda: self.set_mode("rectangle"),
                        )
                        dpg.add_button(
                            label="Polygon [P]",
                            tag="polygon_tool",
                            show=False,
                            callback=lambda: self.set_mode("polygon"),
                        )
                        dpg.add_button(label="Select [V]", callback=lambda: self.set_mode("select"))
                        dpg.add_button(label="Fit [F]", callback=lambda: self.fit())
                        dpg.add_text("100%", tag="zoom")
                    dpg.add_text("Open an image to begin", tag="image_title", color=(177, 190, 207))
                    dpg.add_drawlist(width=760, height=530, tag="canvas")
                    dpg.add_text(
                        "R draw  /  V select  /  Wheel zoom  /  Space + drag pan",
                        tag="canvas_help",
                        color=(130, 146, 166),
                        wrap=780,
                    )
                with dpg.child_window(width=250, tag="inspector"):
                    dpg.add_text("CLASSES")
                    with dpg.group(tag="class_list"):
                        pass
                    dpg.add_separator()
                    dpg.add_checkbox(label="Verified empty", tag="verified_empty", callback=self.mark_empty)
                    dpg.add_text("OBJECTS", tag="objects_title")
                    with dpg.child_window(tag="objects", height=240, border=False):
                        pass
                    dpg.add_text("Select a shape to edit its class.", wrap=220, color=(145, 160, 180))
                    dpg.add_button(
                        label="Delete shape",
                        width=-1,
                        callback=lambda: self.delete_selected(whole_shape=True),
                    )
                    with dpg.group(horizontal=True):
                        dpg.add_button(label="Undo", callback=lambda: self.undo())
                        dpg.add_button(label="Redo", callback=lambda: self.redo())
                    dpg.add_separator()
                    dpg.add_text("No editing lease", tag="lease", wrap=220)
                    dpg.add_text("Not saved", tag="saved", wrap=220)
            dpg.add_separator()
            with dpg.group(horizontal=True):
                dpg.add_button(label="Previous [A]", callback=lambda: self.navigate(-1))
                dpg.add_button(label="Next [D]", callback=lambda: self.navigate(1))
                dpg.add_button(label="Save [Ctrl+S]", callback=lambda: self.save())
                dpg.add_checkbox(label="Autosave (2 seconds)", default_value=True, tag="autosave")
                dpg.add_button(label="Last import report", callback=lambda: dpg.show_item("import_report"))
                dpg.add_button(label="Statistics / QC", callback=lambda: self.statistics.open())
                dpg.add_button(label="Export YOLO", callback=lambda: self.exports.open())
            dpg.add_text(self.status, tag="status", wrap=1200, color=(182, 200, 218))
        with dpg.window(
            label="Connect to DataTracking",
            tag="connection",
            modal=True,
            show=True,
            width=460,
            no_resize=True,
            pos=(360, 180),
            no_close=True,
        ):
            dpg.add_text("Local annotation service", color=(76, 201, 166))
            dpg.add_input_text(label="Server", tag="server", default_value=self.client.url, width=320)
            dpg.add_input_text(label="Username", tag="username", default_value="admin", width=320)
            dpg.add_input_text(
                label="Password",
                tag="password",
                password=True,
                width=320,
                on_enter=True,
                callback=lambda: self.connect(),
            )
            dpg.add_button(label="Connect", callback=lambda: self.connect())
            dpg.add_button(label="Cancel", callback=lambda: dpg.hide_item("connection"))
            dpg.add_text(
                "Run datatracking init and datatracking serve first.", wrap=420, color=(160, 173, 190)
            )
        with dpg.window(
            label="Create project", tag="new_project", modal=True, show=False, width=480, pos=(360, 180)
        ):
            dpg.add_input_text(label="Name", tag="project_name", width=330)
            dpg.add_input_text(label="Slug", tag="project_slug", hint="example-project", width=330)
            dpg.add_combo(
                ["detection", "classification", "segmentation"],
                label="Task",
                default_value="detection",
                tag="project_task",
                width=330,
            )
            dpg.add_input_text(label="Classes", tag="project_classes", hint="part, defect", width=330)
            dpg.add_text("Separate class names with commas. Class IDs stay stable.", wrap=430)
            dpg.add_button(label="Create", callback=lambda: self.create_project())
        with dpg.window(
            label="Unsaved changes",
            tag="dirty_dialog",
            modal=True,
            show=False,
            width=510,
            pos=(350, 200),
            no_close=True,
        ):
            dpg.add_text("Choose how to preserve your edits before continuing.")
            dpg.add_button(label="Save and continue", callback=lambda: self.save_then_continue())
            dpg.add_button(
                label="Keep local recovery draft and continue", callback=lambda: self.keep_then_continue()
            )
            dpg.add_button(label="Cancel", callback=lambda: self.cancel_navigation())
        with dpg.window(
            label="Recovery draft found",
            tag="recovery_dialog",
            modal=True,
            show=False,
            width=540,
            pos=(350, 190),
            no_close=True,
        ):
            dpg.add_text("", tag="recovery_message", wrap=500)
            dpg.add_input_text(tag="recovery_compare", multiline=True, readonly=True, width=-1, height=210)
            dpg.add_button(
                label="Restore draft for editing", tag="restore_draft", callback=lambda: self.restore_draft()
            )
            dpg.add_button(
                label="Use server version; keep draft on disk", callback=lambda: self.dismiss_recovery()
            )
            dpg.add_button(label="Discard recovery draft", callback=lambda: self.discard_recovery())
        with dpg.window(
            label="Save conflict", tag="conflict_dialog", modal=True, show=False, width=530, pos=(350, 190)
        ):
            dpg.add_text("The server rejected this save. Your draft is preserved.", wrap=480)
            dpg.add_text("Reload to compare with the server. No automatic overwrite is performed.", wrap=480)
            dpg.add_button(label="Reload and compare", callback=lambda: self.keep_then_reload())
            dpg.add_button(label="Keep editing locally", callback=lambda: dpg.hide_item("conflict_dialog"))
        with dpg.window(
            label="Import report", tag="import_report", show=False, width=720, height=480, pos=(260, 150)
        ):
            dpg.add_text("Every file is reported. Invalid files are not silently imported.", wrap=670)
            dpg.add_input_text(
                tag="import_report_text",
                multiline=True,
                readonly=True,
                width=-1,
                height=-1,
                default_value="No import has completed in this session.",
            )
        with dpg.window(
            label="Import YOLO predictions",
            tag="yolo_dialog",
            modal=True,
            show=False,
            width=650,
            height=470,
            pos=(280, 140),
        ):
            dpg.add_text("Place image.txt beside image.bmp / .png / .jpg in the server inbox.", wrap=600)
            dpg.add_text(
                "Map model class indices to project class names, one index=name per line.\nCheck this against the model's class order before importing.",
                wrap=600,
            )
            dpg.add_input_text(tag="yolo_mapping", multiline=True, width=-1, height=200)
            dpg.add_checkbox(
                label="Treat empty .txt files as verified empty", tag="yolo_empty", default_value=False
            )
            dpg.add_text(
                "Missing labels remain unlabeled. Existing annotations are never overwritten.\nImported predictions open as IN_PROGRESS for correction.",
                wrap=600,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="Preview", callback=lambda: self.start_yolo_import(True))
                dpg.add_button(label="Import predictions", callback=lambda: self.start_yolo_import(False))
                dpg.add_button(label="Cancel", callback=lambda: dpg.hide_item("yolo_dialog"))
        self.team.build()
        self.statistics.build()
        self.exports.build()
        with dpg.handler_registry():
            dpg.add_mouse_click_handler(button=dpg.mvMouseButton_Left, callback=self.mouse_down)
            dpg.add_mouse_double_click_handler(
                button=dpg.mvMouseButton_Left, callback=self.mouse_double_click
            )
            dpg.add_mouse_release_handler(button=dpg.mvMouseButton_Left, callback=self.mouse_up)
            dpg.add_mouse_move_handler(callback=self.mouse_move)
            dpg.add_mouse_wheel_handler(callback=self.mouse_wheel)
            dpg.add_key_press_handler(callback=self.key_press)
        dpg.create_viewport(
            title="VisionLabel - Annotation workspace", width=1440, height=900, min_width=1060, min_height=700
        )
        dpg.setup_dearpygui()
        dpg.set_primary_window("main", True)
        dpg.set_exit_callback(lambda: self.request_exit())
        dpg.show_viewport()

    def show_connection(self):
        if self.editor.dirty:
            self.guard(lambda: dpg.show_item("connection"))
        else:
            dpg.show_item("connection")

    def connect(self):
        if self.busy or self.saving:
            return
        url, username, password = (dpg.get_value(t) for t in ("server", "username", "password"))
        self.busy = True
        self.message("Connecting...")
        previous_client = self.client
        previous_store = self.store
        previous_image_id = self.image["id"] if self.image else None
        previous_claim = self.claim

        def work():
            client = Client(url)
            try:
                user = client.login(username, password)
                projects = client.list_all("/projects")
                if previous_image_id and previous_claim:
                    try:
                        previous_client.request(
                            "DELETE", f"/images/{previous_image_id}/claim", claim=previous_claim
                        )
                    except Problem:
                        pass  # Reconnecting can succeed while the former server is offline.
                if previous_store:
                    previous_store.clear_cache()
                return client, user, projects
            except Exception:
                client.close()
                raise

        def success(result):
            old = self.client
            self.client, user, self.projects = result
            old.close()
            self.store = LocalStore(self.client.url, user["id"])
            self.image = self.head = self.claim = self.project = None
            self.images = []
            self.pending_save = None
            self.recovery = None
            self.editor.load(empty_content())
            self.busy = False
            dpg.set_value("password", "")
            dpg.hide_item("connection")
            self.populate_projects()
            self.message("Connected. Choose a project or create one.")

        self.submit(work, success)

    def populate_projects(self):
        dpg.configure_item("projects", items=[p["name"] + "  [" + p["slug"] + "]" for p in self.projects])
        if self.projects:
            display = self.projects[0]["name"] + "  [" + self.projects[0]["slug"] + "]"
            dpg.set_value("projects", display)
            self.select_project(None, display)

    def select_project(self, sender, value):
        match = next((p for p in self.projects if p["name"] + "  [" + p["slug"] + "]" == value), None)
        if match:
            self.guard(lambda: self.load_project(match["id"]))

    def load_project(self, project_id):
        if self.busy or self.saving:
            return
        self.release_current()
        self.busy = True
        self.image = None
        self.images = []
        self.populate_images()
        self.head = None
        self.pending_save = None
        self.canvas.cancel()
        self.editor.load(empty_content())
        self.message("Loading project...")

        def success(project):
            self.project = project
            if not any(p["id"] == project["id"] for p in self.projects):
                self.projects.append(project)
                dpg.configure_item(
                    "projects", items=[p["name"] + "  [" + p["slug"] + "]" for p in self.projects]
                )
            dpg.set_value("projects", project["name"] + "  [" + project["slug"] + "]")
            self.canvas = (
                PolygonCanvas(self.editor) if project["task_type"] == "segmentation" else Canvas(self.editor)
            )
            self.busy = False
            self.class_id = project["schema"]["entries"][0]["class_id"]
            self.populate_classes()
            dpg.configure_item("verified_empty", show=project["task_type"] != "classification")
            dpg.configure_item("rectangle_tool", show=project["task_type"] == "detection")
            dpg.configure_item("polygon_tool", show=project["task_type"] == "segmentation")
            dpg.set_value(
                "canvas_help",
                "P: add points / Enter: close / Esc: cancel / V: select / Del: vertex / Double-click edge: insert"
                if project["task_type"] == "segmentation"
                else "R draw / V select / Wheel zoom / Space + drag pan",
            )
            self.refresh_images()
            self.render()

        self.submit(lambda: self.client.request("GET", "/projects/" + project_id), success)

    def create_project(self):
        if not self.client.user or self.busy:
            self.message("Connect before creating a project.")
            return
        body = {
            "name": dpg.get_value("project_name"),
            "slug": dpg.get_value("project_slug"),
            "task_type": dpg.get_value("project_task"),
            "initial_classes": [s.strip() for s in dpg.get_value("project_classes").split(",")],
        }
        self.busy = True
        request_key = uid()

        def success(project):
            self.busy = False
            dpg.hide_item("new_project")
            self.projects.append(project)
            dpg.configure_item("projects", items=[p["name"] + "  [" + p["slug"] + "]" for p in self.projects])
            dpg.set_value("projects", project["name"] + "  [" + project["slug"] + "]")
            self.guard(lambda: self.load_project(project["id"]))

        self.submit(lambda: self.client.request("POST", "/projects", body, key=request_key), success)

    def populate_classes(self):
        dpg.delete_item("class_list", children_only=True)
        if not self.project:
            return
        for index, entry in enumerate(self.project["schema"]["entries"]):
            label = f"{index + 1}. {entry['display_name']}"
            dpg.add_selectable(
                label=label,
                default_value=entry["class_id"] == self.class_id,
                parent="class_list",
                callback=lambda s, a, u: self.select_class(u),
                user_data=entry["class_id"],
            )

    def select_class(self, class_id):
        self.class_id = class_id
        if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft:
            self.canvas.draft_class = class_id
            self.populate_classes()
            self.render()
            return
        if self.image and self.project and not self.busy and self.can_edit():
            data = copy.deepcopy(self.editor.content)
            if self.project["task_type"] == "classification":
                data["image_labels"] = [class_id]
                self.editor.change(data)
            elif self.editor.selected:
                for shape in data["shapes"]:
                    if shape["id"] == self.editor.selected:
                        shape["class_id"] = class_id
                self.editor.change(data)
            self.edited()
        self.populate_classes()

    def refresh_images(self):
        if not self.project:
            return
        search = quote(dpg.get_value("search"))
        status = dpg.get_value("filter")
        project_id = self.project["id"]
        path = f"/projects/{project_id}/images?search={search}&status=" + ("" if status == "All" else status)

        def success(items):
            if self.project and self.project["id"] == project_id:
                self.images = items
                self.populate_images()
                self.message(f"{len(items)} images. Select one to begin.")

        self.submit(lambda: self.client.list_all(path), success)

    def populate_images(self):
        dpg.delete_item("image_list", children_only=True)
        dpg.set_value("image_count", f"{len(self.images)} images")
        for image in self.images:
            label = image["display_filename"] + "\n" + image["status"].replace("_", " ").title()
            dpg.add_selectable(
                label=label,
                parent="image_list",
                default_value=bool(self.image and self.image["id"] == image["id"]),
                callback=lambda s, a, u: self.guard(lambda: self.open_image(u)),
                user_data=image["id"],
            )

    def show_yolo_import(self):
        if not self.project or self.project["task_type"] != "detection":
            self.message("Choose a detection project to import YOLO rectangles.")
            return
        entries = self.project["schema"]["entries"]
        schema_key = (self.project["id"], self.project["active_schema_id"])
        if self.yolo_schema_key != schema_key:
            dpg.set_value(
                "yolo_mapping",
                "\n".join(f"{e['export_index']}={e['display_name']}" for e in entries if e["active"]),
            )
            dpg.set_value("yolo_empty", False)
            self.yolo_schema_key = schema_key
        dpg.show_item("yolo_dialog")

    def start_yolo_import(self, dry_run):
        if not self.project:
            return
        names = {e["display_name"]: e["class_id"] for e in self.project["schema"]["entries"] if e["active"]}
        mapping = {}
        for line in dpg.get_value("yolo_mapping").splitlines():
            if not line.strip():
                continue
            index, separator, name = line.partition("=")
            index, name = index.strip(), name.strip()
            if (
                not separator
                or not index.isascii()
                or not index.isdecimal()
                or index in mapping
                or name not in names
            ):
                self.message("Use unique integer indices and exact project class names: 0=part")
                return
            mapping[index] = names[name]
        if not mapping:
            self.message("Add at least one model class mapping.")
            return
        options = {
            "class_schema_id": self.project["active_schema_id"],
            "class_mapping": mapping,
            "empty_is_verified": dpg.get_value("yolo_empty"),
        }
        dpg.hide_item("yolo_dialog")
        self.import_inbox(options, dry_run)

    def import_inbox(self, yolo=None, dry_run=False):
        if not self.project or self.job:
            self.message("Choose a project first, and wait for any active import.")
            return
        project_id = self.project["id"]
        request_key = uid()
        self.message("Scanning the server import inbox...")

        def work():
            source = self.client.request("GET", f"/projects/{project_id}/import-sources")
            if not source["relative_paths"]:
                raise Problem("EMPTY_INBOX", "No PNG/JPEG/BMP files found in the server inbox.")
            return self.client.request(
                "POST",
                f"/projects/{project_id}/imports",
                dict(source, dry_run=dry_run, yolo=yolo),
                key=request_key,
            )

        def success(result):
            self.job = result["job_id"]
            self.yolo_job = bool(yolo)
            self.job_time = 0
            self.message("Import queued. You can continue editing.")

        self.submit(work, success)

    def release_current(self):
        if self.image and self.claim:
            image_id, claim, client = self.image["id"], self.claim, self.client
            self.submit(
                lambda: client.request("DELETE", f"/images/{image_id}/claim", claim=claim),
                lambda _: None,
                lambda _: None,
            )
        self.claim = None

    def open_image(self, image_id):
        if self.busy or self.saving:
            return
        assert self.store is not None and self.project is not None
        old_image_id = self.image["id"] if self.image else None
        old_claim = self.claim
        self.claim = None
        self.busy = True
        self.blocked = False
        self.pending_save = None
        self.message("Loading image and acquiring editing lease...")
        request_key = uid()
        client, store = self.client, self.store
        project_id = self.project["id"]

        def work():
            if old_image_id and old_claim:
                try:
                    client.request("DELETE", f"/images/{old_image_id}/claim", claim=old_claim)
                except Problem as exc:
                    if exc.status not in (409, 423):
                        raise
            image = client.request("GET", f"/images/{image_id}")
            if image["project_id"] != project_id:
                raise Problem(
                    "PROJECT_CHANGED", "This image belongs to another project. Refresh the image list.", 409
                )
            claim_error = None
            try:
                claim = client.request(
                    "POST",
                    f"/images/{image_id}/claim",
                    {"mode": "edit", "client_instance_id": client.instance},
                    key=request_key,
                )
            except Problem as exc:
                if exc.status not in (403, 409, 423):
                    raise
                claim, claim_error = None, exc.message
            head = client.request("GET", f"/images/{image_id}/annotation")
            data = store.read_cached(image)
            if data is None:
                data = store.cached_image(
                    image, client.request("GET", f"/images/{image_id}/content", raw=True)
                )
            width, height, pixels, _ = store.decode_image(image, data)
            texture = array("f", (component / 255 for component in pixels))
            draft = store.load_draft(image_id)
            return image, claim, head, width, height, texture, draft, claim_error

        def success(result):
            assert self.project is not None
            self.image, self.claim, self.head, width, height, pixels, draft, claim_error = result
            assert self.image is not None and self.head is not None
            self.editor.load(self.content_from_head(self.head))
            self.last_content = canonical(self.editor.content)
            self.canvas.cancel()
            self.canvas.width, self.canvas.height = self.image["width"], self.image["height"]
            dpg.delete_item("canvas", children_only=True)
            if self.texture:
                dpg.delete_item(self.texture)
            self.texture_number += 1
            self.texture = f"image_texture_{self.texture_number}"
            dpg.add_static_texture(width, height, pixels, tag=self.texture, parent="textures")
            self.busy = False
            self.heartbeat_failures = 0
            self.heartbeat_time = time.monotonic()
            self.fit()
            self.populate_images()
            dpg.set_value(
                "image_title",
                f"{self.image['display_filename']}  /  {self.image['width']} x {self.image['height']} px",
            )
            ready = {
                "segmentation": "Ready. Use P to add polygon points, Enter to finish, or V to select.",
                "classification": "Ready. Choose one class for this image.",
                "detection": "Ready. Draw a rectangle, or use V to select and move.",
            }
            self.message(claim_error or ready[self.project["task_type"]])
            self.render()
            if draft:
                self.recovery = draft
                self.blocked = True
                same = (
                    draft["base_revision"] == self.head["revision"]
                    and draft.get("base_hash") == self.head["annotation_sha256"]
                    and draft["schema_id"] == self.project["active_schema_id"]
                )
                dpg.set_value(
                    "recovery_message",
                    "A local recovery draft matches the server base. Restore it to continue editing."
                    if same
                    else "The server changed since this draft. Compare below. The old draft stays on disk; use the server version and manually reapply the edits you need.",
                )
                compare = {
                    "local_base_revision": draft["base_revision"],
                    "server_revision": self.head["revision"],
                    "local_content": draft["content"],
                    "server_content": self.editor.content,
                }
                dpg.set_value("recovery_compare", json.dumps(compare, indent=2, ensure_ascii=False))
                dpg.configure_item("restore_draft", enabled=same and bool(self.claim))
                dpg.show_item("recovery_dialog")

        self.submit(work, success)

    @staticmethod
    def content_from_head(head):
        doc = head["annotation"]
        return (
            {k: copy.deepcopy(doc[k]) for k in ("verified_empty", "image_labels", "shapes")}
            if doc
            else empty_content()
        )

    def restore_draft(self):
        assert self.recovery is not None
        self.editor.change(self.recovery["content"])
        self.blocked = False
        dpg.hide_item("recovery_dialog")
        self.edited()

    def dismiss_recovery(self):
        if self.store and self.image:
            self.store.archive_draft(self.image["id"])
        self.recovery = None
        self.blocked = False
        dpg.hide_item("recovery_dialog")

    def discard_recovery(self):
        assert self.store is not None and self.image is not None
        self.store.remove_draft(self.image["id"])
        self.recovery = None
        self.dismiss_recovery()

    def reload(self):
        if self.image:
            self.open_image(self.image["id"])

    def keep_then_reload(self):
        self.persist_draft()
        dpg.hide_item("conflict_dialog")
        self.reload()

    def guard(self, action):
        if self.busy or self.saving:
            self.message("Wait for the current load or save to finish.")
            return
        if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft:
            self.message("Finish the polygon with Enter, or cancel it with Escape before continuing.")
            return
        if self.editor.dirty or self.pending_save:
            self.next_action = action
            dpg.show_item("dirty_dialog")
        else:
            action()

    def save_then_continue(self):
        self.save(continue_after=True)

    def keep_then_continue(self):
        self.persist_draft()
        dpg.hide_item("dirty_dialog")
        action, self.next_action = self.next_action, None
        if action:
            action()

    def cancel_navigation(self):
        self.next_action = None
        dpg.hide_item("dirty_dialog")

    def navigate(self, delta):
        if not self.images:
            return
        current_id = self.image["id"] if self.image else None
        index = next((i for i, img in enumerate(self.images) if img["id"] == current_id), -1)
        target = max(0, min(len(self.images) - 1, index + delta))
        if target != index:
            self.guard(lambda: self.open_image(self.images[target]["id"]))

    def persist_draft(self):
        if not self.image or not self.store or not self.head or not self.project:
            return
        assert self.client.user is not None
        body = {
            "image_id": self.image["id"],
            "project_id": self.project["id"],
            "user_id": self.client.user["id"],
            "server": self.client.url,
            "schema_id": self.project["active_schema_id"],
            "base_revision": self.head["revision"],
            "base_hash": self.head["annotation_sha256"],
            "base_state_revision": self.head["state_revision"],
            "content": self.editor.content,
            "local_timestamp": datetime.now(UTC).isoformat(),
            "pending_save": self.pending_save,
        }
        self.store.save_draft(self.image["id"], body)

    def edited(self):
        current = canonical(self.editor.content)
        if current != self.last_content:
            self.last_content = current
            self.edit_time = time.monotonic()
            try:
                if self.editor.dirty or self.pending_save:
                    self.persist_draft()
                elif self.store and self.image:
                    self.store.remove_draft(self.image["id"])
            except OSError as exc:
                self.blocked = True
                self.error(exc)
        self.render()

    def save(self, continue_after=False):
        if not self.image or self.busy or self.saving:
            return
        if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft:
            self.message("Finish the polygon with Enter before saving. Escape cancels unfinished points.")
            return
        if self.blocked or not self.claim:
            self.message("Saving is paused. Reload and reconcile your draft first.")
            return
        assert self.head is not None and self.project is not None and self.store is not None
        if not self.editor.dirty and not self.pending_save:
            if continue_after:
                self.keep_then_continue()
            return
        if not self.pending_save:
            self.pending_save = {
                "key": uid(),
                "body": {
                    "expected_revision": self.head["revision"],
                    "expected_state_revision": self.head["state_revision"],
                    "class_schema_id": self.project["active_schema_id"],
                    "content": copy.deepcopy(self.editor.content),
                },
            }
        pending = copy.deepcopy(self.pending_save)
        image_id, claim = self.image["id"], self.claim
        self.persist_draft()
        self.saving = True
        self.message("Saving...")

        def success(result):
            assert self.head is not None and self.image is not None and self.store is not None
            self.saving = False
            self.pending_save = None
            self.head.update(
                {
                    "revision": result["revision"],
                    "state_revision": result["state_revision"],
                    "annotation_sha256": result["annotation_sha256"],
                    "status": result["status"],
                }
            )
            self.editor.saved = canonical(pending["body"]["content"])
            self.image["status"] = result["status"]
            for image in self.images:
                if image["id"] == image_id:
                    image["status"] = result["status"]
            if self.editor.dirty:
                self.persist_draft()
                self.edit_time = time.monotonic()
            else:
                self.store.remove_draft(image_id)
            self.message(f"Saved revision {result['revision']}.")
            self.render()
            self.populate_images()
            if continue_after and not self.editor.dirty:
                dpg.hide_item("dirty_dialog")
                action, self.next_action = self.next_action, None
                if action:
                    action()

        def failure(exc):
            self.saving = False
            self.error(exc)
            if isinstance(exc, Problem) and exc.status in (401, 403, 404, 409, 423):
                self.blocked = True
                dpg.show_item("conflict_dialog")
            elif isinstance(exc, Problem) and exc.status == 422:
                self.pending_save = None
                dpg.set_value("autosave", False)
                self.message(exc.message + " Correct the annotation and save again. Autosave is paused.")
            else:
                self.edit_time = time.monotonic() + 3
            self.persist_draft()

        self.submit(
            lambda: self.client.request(
                "PUT", f"/images/{image_id}/annotation", pending["body"], claim=claim, key=pending["key"]
            ),
            success,
            failure,
        )

    def set_mode(self, mode):
        if self.project:
            allowed = "polygon" if self.project["task_type"] == "segmentation" else "rectangle"
            if mode not in (allowed, "select") or self.project["task_type"] == "classification":
                return
        if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft:
            self.message("Finish with Enter or cancel with Escape before switching tools.")
            return
        self.canvas.mode = mode
        self.update_crosshair()
        self.message(
            "Polygon tool: click to add points; Enter or double-click to finish; Escape to cancel."
            if mode == "polygon"
            else "Rectangle tool: drag to create. Selected handles remain resizable."
            if mode == "rectangle"
            else "Select tool: click a box, then drag it or its handles."
        )

    def fit(self):
        if self.image:
            self.canvas.transform.fit(
                self.canvas.width,
                self.canvas.height,
                dpg.get_item_width("canvas"),
                dpg.get_item_height("canvas"),
            )
        self.render()

    def mark_empty(self, sender, value):
        if not self.image or self.busy or not self.can_edit():
            dpg.set_value("verified_empty", False)
            return
        if value and self.editor.content["shapes"]:
            dpg.set_value("verified_empty", False)
            self.message("Delete existing rectangles before marking the image verified empty.")
            return
        data = copy.deepcopy(self.editor.content)
        data["verified_empty"] = value
        self.editor.change(data)
        self.edited()

    def delete_selected(self, whole_shape=False):
        if not self.image or self.busy or not self.can_edit():
            return
        if isinstance(self.canvas, PolygonCanvas):
            if self.canvas.draft:
                self.canvas.draft.pop()
                self.render()
                return
            if not whole_shape:
                try:
                    if self.canvas.delete_vertex():
                        self.edited()
                        return
                except Problem as exc:
                    self.message(exc.message)
                    return
            self.canvas.selected_vertex = None
        data = copy.deepcopy(self.editor.content)
        data["shapes"] = [s for s in data["shapes"] if s["id"] != self.editor.selected]
        self.editor.change(data)
        self.editor.selected = None
        self.edited()

    def undo(self):
        if self.image and not self.busy and self.can_edit():
            if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft:
                self.canvas.draft.pop()
                self.render()
                return
            self.canvas.cancel()
            self.editor.undo()
            self.edited()

    def redo(self):
        if self.image and not self.busy and self.can_edit():
            if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft:
                self.message("Finish or cancel the unfinished polygon before redo.")
                return
            self.canvas.cancel()
            self.editor.redo()
            self.edited()

    def modal_open(self):
        return any(
            dpg.is_item_shown(tag)
            for tag in (
                "connection",
                "new_project",
                "dirty_dialog",
                "recovery_dialog",
                "conflict_dialog",
                "team",
                "statistics",
                "yolo_dialog",
                "export_dialog",
                "export_folder_picker",
            )
        )

    def can_edit(self):
        return bool(self.project and self.project.get("can_edit", True))

    def mouse_position(self):
        mx, my = dpg.get_mouse_pos(local=False)
        x, y = dpg.get_item_rect_min("canvas")
        return mx - x, my - y

    def mouse_down(self, sender, value):
        if (
            self.canvas.gesture
            or self.busy
            or self.modal_open()
            or not self.image
            or not dpg.is_item_hovered("canvas")
        ):
            return
        pan = dpg.is_key_down(dpg.mvKey_Spacebar)
        if not pan and not self.can_edit():
            return
        assert self.project is not None
        if self.project["task_type"] == "classification" and not pan:
            return
        x, y = self.mouse_position()
        try:
            self.canvas.start(x, y, self.class_id, pan=pan)
            self.edited()
        except Problem as exc:
            self.message(exc.message)
            self.render()

    def mouse_double_click(self, sender, value):
        if (
            not isinstance(self.canvas, PolygonCanvas)
            or not self.image
            or self.busy
            or self.modal_open()
            or not self.can_edit()
            or not dpg.is_item_hovered("canvas")
            or dpg.is_key_down(dpg.mvKey_Spacebar)
        ):
            return
        try:
            if self.canvas.mode == "polygon":
                self.canvas.finish_polygon()
            else:
                self.canvas.insert_vertex(*self.mouse_position())
            self.edited()
        except Problem as exc:
            self.message(exc.message)
            self.render()

    def finish_polygon(self):
        if isinstance(self.canvas, PolygonCanvas) and self.can_edit():
            try:
                self.canvas.finish_polygon()
                self.edited()
            except Problem as exc:
                self.message(exc.message)
                self.render()

    def mouse_move(self, sender, value):
        if self.canvas.gesture or (isinstance(self.canvas, PolygonCanvas) and self.canvas.draft):
            self.canvas.move(*self.mouse_position())
            self.render(canvas_only=True)
        else:
            self.update_crosshair()

    def update_crosshair(self):
        # A separate overlay avoids rebuilding every annotation on pointer movement.
        if dpg.does_item_exist("crosshair"):
            dpg.delete_item("crosshair")
        self.crosshair_visible = False
        if (
            not self.image
            or not self.texture
            or not self.project
            or self.project["task_type"] != "detection"
            or self.canvas.mode != "rectangle"
            or not self.can_edit()
            or self.busy
            or self.modal_open()
            or dpg.is_item_shown("import_report")
            or dpg.is_item_shown("yolo_dialog")
            or not dpg.is_item_hovered("canvas")
            or dpg.is_key_down(dpg.mvKey_Spacebar)
            or (self.canvas.gesture and self.canvas.gesture["kind"] == "pan")
        ):
            return
        x, y = self.mouse_position()
        left, top = self.canvas.transform.screen(0, 0)
        right, bottom = self.canvas.transform.screen(self.canvas.width, self.canvas.height)
        left, top = max(0, left), max(0, top)
        right = min(dpg.get_item_width("canvas"), right)
        bottom = min(dpg.get_item_height("canvas"), bottom)
        if not (left <= x <= right and top <= y <= bottom):
            return
        with dpg.draw_layer(tag="crosshair", parent="canvas"):
            # Dark outline and light core stay visible against bright and dark images.
            for color, thickness in (((0, 0, 0, 210), 3), ((255, 255, 255, 235), 1)):
                dpg.draw_line((left, y), (right, y), color=color, thickness=thickness)
                dpg.draw_line((x, top), (x, bottom), color=color, thickness=thickness)
        self.crosshair_visible = True

    def update_pointer_icon(self):
        # Apply after ImGui renders its cursor. SetCursor does not alter the global
        # ShowCursor counter or replace any system cursor resources.
        if self.crosshair_visible:
            self.cursor_api.SetCursor(self.crosshair_cursor)
            self.crosshair_cursor_owned = True
        elif self.crosshair_cursor_owned:
            self.cursor_api.SetCursor(self.arrow_cursor)
            self.crosshair_cursor_owned = False

    def mouse_up(self, sender, value):
        if self.canvas.gesture:
            try:
                self.canvas.finish()
                self.edited()
            except Problem as exc:
                self.message(exc.message + " The previous valid shape was kept.")
                self.render()

    def mouse_wheel(self, sender, value):
        if self.image and not self.modal_open() and dpg.is_item_hovered("canvas"):
            x, y = self.mouse_position()
            self.canvas.transform.zoom(x, y, 1.15**value)
            self.render(canvas_only=True)

    def key_press(self, sender, key):
        if self.modal_open() or any(dpg.is_item_active(tag) for tag in self.text_inputs) or self.busy:
            return
        control = dpg.is_key_down(dpg.mvKey_LControl) or dpg.is_key_down(dpg.mvKey_RControl)
        if control:
            if key == dpg.mvKey_S:
                self.save()
            elif key == dpg.mvKey_Z:
                self.undo()
            elif key == dpg.mvKey_Y:
                self.redo()
            return
        actions: dict[int, Callable[[], None]] = {
            dpg.mvKey_R: lambda: self.set_mode("rectangle"),
            dpg.mvKey_P: lambda: self.set_mode("polygon"),
            dpg.mvKey_Return: self.finish_polygon,
            dpg.mvKey_V: lambda: self.set_mode("select"),
            dpg.mvKey_F: self.fit,
            dpg.mvKey_Delete: self.delete_selected,
            dpg.mvKey_A: lambda: self.navigate(-1),
            dpg.mvKey_D: lambda: self.navigate(1),
            dpg.mvKey_Escape: self.canvas.cancel,
        }
        if key in actions:
            actions[key]()
            self.render()
        if self.project:
            for i, entry in enumerate(self.project["schema"]["entries"][:9]):
                if key == getattr(dpg, f"mvKey_{i + 1}"):
                    self.select_class(entry["class_id"])

    def render(self, canvas_only=False):
        dpg.delete_item("canvas", children_only=True)
        width, height = dpg.get_item_width("canvas"), dpg.get_item_height("canvas")
        dpg.draw_rectangle((0, 0), (width, height), fill=(12, 16, 22), color=(38, 46, 58), parent="canvas")
        if self.image and self.texture:
            assert self.project is not None
            t = self.canvas.transform
            dpg.draw_image(
                self.texture, t.screen(0, 0), t.screen(self.canvas.width, self.canvas.height), parent="canvas"
            )
            classes = {c["class_id"]: c for c in self.project["schema"]["entries"]}
            data = self.canvas.preview or self.editor.content
            for shape in data["shapes"]:
                entry = classes[shape["class_id"]]
                color = tuple(bytes.fromhex(entry["color_hex"].lstrip("#")))
                selected = shape["id"] == self.editor.selected
                if shape["type"] == "polygon":
                    points = [t.screen(*p) for p in shape["points"]]
                    p1 = min(points)
                    dpg.draw_polyline(
                        points, closed=True, color=color, thickness=2.5 if selected else 1.5, parent="canvas"
                    )
                else:
                    p1, p2 = t.screen(shape["x1"], shape["y1"]), t.screen(shape["x2"], shape["y2"])
                    dpg.draw_rectangle(
                        p1,
                        p2,
                        color=color,
                        fill=(*color, 20 if selected else 8),
                        thickness=2.5 if selected else 1.5,
                        parent="canvas",
                    )
                dpg.draw_text(
                    (p1[0] + 4, p1[1] + 3), entry["display_name"], size=15, color=color, parent="canvas"
                )
                if selected:
                    for index, (x, y) in enumerate(self.canvas.handles(shape)):
                        sx, sy = t.screen(x, y)
                        vertex_selected = (
                            isinstance(self.canvas, PolygonCanvas) and self.canvas.selected_vertex == index
                        )
                        dpg.draw_rectangle(
                            (sx - 4, sy - 4),
                            (sx + 4, sy + 4),
                            fill=(255, 255, 255) if vertex_selected else color,
                            color=(240, 250, 255),
                            parent="canvas",
                        )
            if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft:
                points = [t.screen(*p) for p in self.canvas.draft]
                if self.canvas.hover:
                    points.append(t.screen(*self.canvas.hover))
                if len(points) > 1:
                    dpg.draw_polyline(points, color=(255, 220, 100), thickness=2, parent="canvas")
                for point in points[:-1]:
                    dpg.draw_circle(point, 4, color=(255, 220, 100), fill=(255, 220, 100), parent="canvas")
            dpg.set_value("zoom", f"{t.scale * 100:.0f}%")
        else:
            dpg.draw_text(
                (35, 50), "Your annotation workspace", size=24, color=(187, 203, 221), parent="canvas"
            )
            dpg.draw_text(
                (35, 90),
                "Connect, choose a project, and open an image.",
                size=16,
                color=(130, 148, 172),
                parent="canvas",
            )
        self.update_crosshair()
        if canvas_only:
            return
        dpg.set_value("verified_empty", self.editor.content["verified_empty"])
        dpg.set_value(
            "lease",
            "Editing lease active"
            if self.claim and not self.blocked
            else "Local editing / shared save paused"
            if self.image
            else "No editing lease",
        )
        dpg.set_value(
            "saved",
            f"Revision {self.head['revision']}  /  "
            + (
                "Unfinished polygon: Enter to close"
                if isinstance(self.canvas, PolygonCanvas) and self.canvas.draft
                else "Unsaved changes"
                if self.editor.dirty
                else "Saved"
            )
            if self.head
            else "Not saved",
        )
        dpg.set_value("objects_title", f"OBJECTS  /  {len(self.editor.content['shapes'])}")
        dpg.delete_item("objects", children_only=True)
        if self.project:
            classes = {c["class_id"]: c for c in self.project["schema"]["entries"]}
            for index, shape in enumerate(self.editor.content["shapes"]):
                geometry = (
                    f"{len(shape['points'])} vertices"
                    if shape["type"] == "polygon"
                    else f"{shape['x2'] - shape['x1']:.0f} x {shape['y2'] - shape['y1']:.0f}"
                )
                dpg.add_selectable(
                    label=f"{index + 1}. {classes[shape['class_id']]['display_name']}  ({geometry})",
                    default_value=shape["id"] == self.editor.selected,
                    parent="objects",
                    callback=lambda s, a, u: self.select_shape(u),
                    user_data=shape["id"],
                )
            if self.project["task_type"] == "classification":
                labels = self.editor.content["image_labels"]
                dpg.add_text(
                    "Label: " + (classes[labels[0]]["display_name"] if labels else "Not labeled"),
                    parent="objects",
                    wrap=215,
                )

    def select_shape(self, shape_id):
        if isinstance(self.canvas, PolygonCanvas):
            if self.canvas.draft:
                self.message("Finish or cancel the unfinished polygon before selecting another shape.")
                return
            self.canvas.selected_vertex = None
        self.editor.selected = shape_id
        self.canvas.mode = "select"
        self.render()

    def tick(self):
        while not self.completed.empty():
            callback, value, is_error = self.completed.get_nowait()
            try:
                callback(value)
            except Exception as exc:
                self.error(exc)
        current = time.monotonic()
        if (
            self.image
            and self.claim
            and not self.busy
            and not self.heartbeat_pending
            and current - self.heartbeat_time >= 45
        ):
            self.heartbeat_pending = True
            self.heartbeat_time = current
            image_id, claim = self.image["id"], self.claim

            def success(result):
                self.heartbeat_pending = False
                if self.image and self.image["id"] == image_id and self.claim == claim:
                    self.claim["expires_at"] = result["expires_at"]
                    self.heartbeat_failures = 0

            def failure(exc):
                self.heartbeat_pending = False
                if self.image and self.image["id"] == image_id:
                    self.heartbeat_failures += 1
                    if self.heartbeat_failures >= 2 or (isinstance(exc, Problem) and exc.status == 409):
                        self.blocked = True
                        self.persist_draft()
                        self.error(exc)
                        self.render()

            self.submit(
                lambda: self.client.request("POST", f"/images/{image_id}/claim/heartbeat", claim=claim),
                success,
                failure,
            )
        if self.claim and self.claim["expires_at"] <= datetime.now(UTC).isoformat(
            timespec="microseconds"
        ).replace("+00:00", "Z"):
            self.blocked = True
        if (
            self.image
            and self.editor.dirty
            and not self.canvas.gesture
            and not (isinstance(self.canvas, PolygonCanvas) and self.canvas.draft)
            and not self.blocked
            and not self.modal_open()
            and dpg.get_value("autosave")
            and current - self.edit_time >= 2
        ):
            self.save()
        if self.job and not self.job_pending and current - self.job_time > 0.75:
            self.job_time = current
            self.job_pending = True
            job_id = self.job

            def job_result(result):
                self.job_pending = False
                progress = result["progress"]
                self.message(f"Import {result['state']}: {progress['done']}/{progress['total']}")
                if result["state"] in ("succeeded", "failed", "cancelled"):
                    self.job = None
                    self.refresh_images()
                    items = (result.get("result") or {}).get("items", [])
                    dpg.set_value("import_report_text", json.dumps(result, indent=2, ensure_ascii=False))
                    failed = sum(item["outcome"] == "invalid" for item in items)
                    if self.yolo_job or failed or result["state"] == "failed":
                        dpg.show_item("import_report")
                    self.message(
                        f"Import {result['state']}: {len(items)} checked, {failed} invalid. Full report: job {job_id}"
                    )

            def job_error(exc):
                self.job_pending = False
                self.error(exc)

            self.submit(lambda: self.client.request("GET", f"/jobs/{job_id}"), job_result, job_error)
        height = max(450, dpg.get_viewport_client_height() - 170)
        width = max(380, dpg.get_item_rect_size("center")[0] - 28)
        for tag in ("sidebar", "center", "inspector"):
            if dpg.get_item_height(tag) != height:
                dpg.configure_item(tag, height=height)
        if dpg.get_item_width("canvas") != width or dpg.get_item_height("canvas") != height - 125:
            dpg.configure_item("canvas", width=width, height=height - 125)
            self.render(canvas_only=True)

        self.update_crosshair()

    def request_exit(self):
        # Closing the native window cannot wait for network IO. Preserve a private draft.
        if self.editor.dirty or self.pending_save:
            self.persist_draft()
        self.exit_requested = True

    def run(self, smoke_frames=0, screenshot=None):
        self.build()
        try:
            while dpg.is_dearpygui_running() and not self.exit_requested:
                dpg.run_callbacks(dpg.get_callback_queue())
                self.tick()
                dpg.render_dearpygui_frame()
                self.update_pointer_icon()
                self.frame_count += 1
                if screenshot and self.frame_count == max(5, smoke_frames - 5):
                    dpg.output_frame_buffer(str(screenshot))
                if smoke_frames and self.frame_count >= smoke_frames:
                    break
        finally:
            self.crosshair_visible = False
            self.update_pointer_icon()
            self.request_exit()
            self.release_current()
            self.pool.shutdown(wait=True)
            self.client.close()
            dpg.destroy_context()


def main():
    parser = argparse.ArgumentParser(description="VisionLabel rectangle workspace")
    parser.add_argument("--server", default="http://127.0.0.1:8765")
    parser.add_argument("--smoke-frames", type=int, default=0)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    Desktop(args.server).run(args.smoke_frames, args.screenshot)


if __name__ == "__main__":
    main()

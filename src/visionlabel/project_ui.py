"""Native project organization, schema templates, history and deliberate remapping."""

import json
from pathlib import Path

import dearpygui.dearpygui as dpg

from .class_mapping import model_names
from .domain import Problem, uid


class ProjectPanel:
    def __init__(self, app):
        self.app = app
        self.busy = False
        self.selected = None
        self.projects = []
        self.folders = {}
        self.folder_choices = {"(Root)": None}
        self.templates = {}
        self.preview = None
        self.preview_keys = {}
        self.preview_generation = 0
        self.image_items = []
        self.image_choices = {}

    def build(self):
        with dpg.window(
            label="Project Manager",
            tag="project_manager",
            modal=True,
            show=False,
            width=1050,
            height=740,
            pos=(90, 35),
        ):
            with dpg.group(horizontal=True):
                dpg.add_button(label="Refresh", callback=lambda: self.refresh())
                dpg.add_input_text(
                    label="Search", tag="pm_search", width=260, callback=lambda: self.render_tree()
                )
                dpg.add_checkbox(
                    label="Show archived", tag="pm_archived_filter", callback=lambda: self.render_tree()
                )
                dpg.add_button(label="New project", callback=self.new_project)
            with dpg.group(horizontal=True):
                with dpg.child_window(tag="pm_tree", width=270, height=550):
                    pass
                with dpg.child_window(width=735, height=550):
                    with dpg.tab_bar():
                        with dpg.tab(label="Project"):
                            dpg.add_input_text(label="Name", tag="pm_name", width=450)
                            dpg.add_input_text(
                                label="Description",
                                tag="pm_description",
                                multiline=True,
                                height=80,
                                width=600,
                            )
                            dpg.add_combo(["(Root)"], tag="pm_folder", label="Folder", width=550)
                            dpg.add_checkbox(label="Archived (restore by unchecking)", tag="pm_archived")
                            dpg.add_button(label="Save project metadata", callback=self.save_project)
                            dpg.add_button(label="Open selected project", callback=self.open_selected)
                            dpg.add_text(
                                "Archive hides the project from the normal list and blocks writes. History is retained.",
                                wrap=640,
                            )
                        with dpg.tab(label="Folders"):
                            dpg.add_combo(
                                ["(Root)"],
                                tag="pm_folder_edit",
                                label="Existing folder",
                                width=550,
                                callback=self.select_folder,
                            )
                            dpg.add_input_text(label="Folder name", tag="pm_folder_name", width=450)
                            dpg.add_combo(["(Root)"], tag="pm_parent", label="Parent", width=550)
                            dpg.add_button(label="Create folder", callback=lambda: self.save_folder(True))
                            dpg.add_button(
                                label="Rename / move folder", callback=lambda: self.save_folder(False)
                            )
                            dpg.add_button(
                                label="Delete empty folder", callback=lambda: self.save_folder(False, True)
                            )
                        with dpg.tab(label="Classes / templates"):
                            dpg.add_input_text(
                                tag="pm_classes", multiline=True, readonly=True, width=650, height=210
                            )
                            dpg.add_text(
                                "Schema indices and class IDs stay stable. Model export mapping is configured in Export YOLO.",
                                wrap=640,
                            )
                            dpg.add_input_text(label="Template name", tag="pm_template_name", width=430)
                            dpg.add_button(
                                label="Save active classes as template", callback=self.save_template
                            )
                            dpg.add_combo([], tag="pm_template", label="Template", width=550)
                            dpg.add_button(label="New project from template", callback=self.new_from_template)
                            dpg.add_text(
                                "Templates copy ordered active class names and task type; they create new class IDs, without images.",
                                wrap=640,
                            )
                        with dpg.tab(label="Versions"):
                            dpg.add_button(
                                label="Refresh working / schema / export history", callback=self.load_versions
                            )
                            dpg.add_input_text(
                                tag="pm_versions", multiline=True, readonly=True, width=650, height=420
                            )
                        with dpg.tab(label="Remap annotations"):
                            dpg.add_text(
                                "Select images deliberately. This changes saved labels, including manual corrections. Preview first; Apply creates new revisions. Individual failures are reported.",
                                wrap=640,
                            )
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="Load images", callback=self.load_images)
                                dpg.add_input_text(
                                    label="Filename search",
                                    tag="pm_image_search",
                                    width=300,
                                    callback=lambda: self.filter_images(),
                                )
                            dpg.add_combo([], tag="pm_image_picker", width=620)
                            with dpg.group(horizontal=True):
                                dpg.add_button(label="Add selected image", callback=self.add_image)
                                dpg.add_button(label="Clear image selection", callback=self.clear_images)
                            dpg.add_input_text(
                                label="Image IDs (one per line)",
                                tag="pm_remap_images",
                                multiline=True,
                                width=600,
                                height=65,
                                callback=self.invalidate_preview,
                            )
                            dpg.add_input_text(
                                label="Source name=destination name",
                                tag="pm_remap_mapping",
                                multiline=True,
                                width=600,
                                height=65,
                                callback=self.invalidate_preview,
                            )
                            dpg.add_button(label="Preview remap", callback=self.preview_remap)
                            dpg.add_input_text(
                                tag="pm_remap_report", multiline=True, readonly=True, width=650, height=170
                            )
                            dpg.add_button(
                                label="Apply preview / retry failed items",
                                tag="pm_remap_apply",
                                enabled=False,
                                callback=self.apply_remap,
                            )
            dpg.add_text("", tag="pm_status", wrap=990)
            dpg.add_button(label="Close", callback=lambda: dpg.hide_item("project_manager"))

    def message(self, value):
        dpg.set_value("pm_status", value)

    def run(self, work, done):
        if self.busy or self.app.busy or self.app.saving:
            return
        self.busy = True
        self.app.busy = True
        for tag in ("pm_remap_images", "pm_remap_mapping"):
            dpg.configure_item(tag, enabled=False)
        client = self.app.client

        def success(value):
            self.busy = False
            self.app.busy = False
            for tag in ("pm_remap_images", "pm_remap_mapping"):
                dpg.configure_item(tag, enabled=True)
            if self.app.client is client:
                done(value)

        def failed(exc):
            self.busy = False
            self.app.busy = False
            for tag in ("pm_remap_images", "pm_remap_mapping"):
                dpg.configure_item(tag, enabled=True)
            self.message(exc.message if isinstance(exc, Problem) else str(exc))

        self.app.submit(work, success, failed)

    def open(self):
        if not self.app.client.user:
            self.app.message("Connect before opening Project Manager.")
            return
        dpg.show_item("project_manager")
        self.refresh()

    def refresh(self):
        client = self.app.client

        def work():
            return (
                client.list_all("/projects?include_archived=true"),
                client.request("GET", "/project-folders"),
                client.request("GET", "/class-templates"),
            )

        def done(result):
            self.projects, folders, templates = result
            self.folders = {f["id"]: f for f in folders["items"]}
            self.folder_choices = {"(Root)": None} | {
                self.folder_path(fid) + " [" + fid + "]": fid for fid in self.folders
            }
            for tag in ("pm_folder", "pm_folder_edit", "pm_parent"):
                dpg.configure_item(tag, items=list(self.folder_choices))
                if dpg.get_value(tag) not in self.folder_choices:
                    dpg.set_value(tag, "(Root)")
            self.templates = {t["name"] + " [" + t["id"] + "]": t for t in templates["items"]}
            dpg.configure_item("pm_template", items=list(self.templates))
            dpg.set_value("pm_template", next(iter(self.templates), ""))
            self.app.projects = [p for p in self.projects if not p["archived"]]
            dpg.configure_item(
                "projects", items=[p["name"] + "  [" + p["slug"] + "]" for p in self.app.projects]
            )
            self.render_tree()
            if self.selected and any(p["id"] == self.selected["id"] for p in self.projects):
                self.select(self.selected["id"])
            else:
                self.selected = None
                self.invalidate_preview()
                for tag in (
                    "pm_name",
                    "pm_description",
                    "pm_classes",
                    "pm_versions",
                    "pm_remap_report",
                    "pm_remap_images",
                ):
                    dpg.set_value(tag, "")
            self.message("Projects refreshed. Select a project to inspect or edit.")

        self.run(work, done)

    def folder_path(self, fid):
        names, seen = [], set()
        while fid in self.folders and fid not in seen:
            seen.add(fid)
            names.append(self.folders[fid]["name"])
            fid = self.folders[fid]["parent_id"]
        return " / ".join(reversed(names))

    def render_tree(self):
        dpg.delete_item("pm_tree", children_only=True)
        search = dpg.get_value("pm_search").casefold()
        show_archived = dpg.get_value("pm_archived_filter")

        def populate(parent_id, widget):
            for folder in self.folders.values():
                if folder["parent_id"] == parent_id:
                    node = dpg.add_tree_node(label=folder["name"], parent=widget, default_open=True)
                    populate(folder["id"], node)
            for project in self.projects:
                if (
                    project["folder_id"] == parent_id
                    and (show_archived or not project["archived"])
                    and search in (project["name"] + " " + project["description"]).casefold()
                ):
                    dpg.add_selectable(
                        label=project["name"] + (" [Archived]" if project["archived"] else ""),
                        parent=widget,
                        callback=lambda s, a, u: self.select(u),
                        user_data=project["id"],
                    )

        populate(None, "pm_tree")

    def select(self, pid):
        if self.busy:
            return
        client = self.app.client

        def done(project):
            self.selected = project
            self.image_items = []
            self.filter_images()
            if self.app.project and self.app.project["id"] == pid:
                self.app.project = project
                dpg.set_value("projects", project["name"] + "  [" + project["slug"] + "]")
            self.invalidate_preview()
            for tag, value in (
                ("pm_name", project["name"]),
                ("pm_description", project["description"]),
                ("pm_archived", bool(project["archived"])),
            ):
                dpg.set_value(tag, value)
            dpg.set_value(
                "pm_folder",
                next(
                    (label for label, fid in self.folder_choices.items() if fid == project["folder_id"]),
                    "(Root)",
                ),
            )
            dpg.set_value(
                "pm_classes",
                "Index | Name | Class ID\n"
                + "\n".join(
                    f"{e['export_index']} | {e['display_name']} | {e['class_id']}"
                    for e in sorted(project["schema"]["entries"], key=lambda e: e["export_index"])
                ),
            )
            dpg.set_value("pm_versions", "Choose Refresh to load version history.")
            dpg.set_value(
                "pm_remap_images",
                self.app.image["id"] if self.app.image and self.app.image["project_id"] == pid else "",
            )

        self.run(lambda: client.request("GET", f"/projects/{pid}"), done)

    def save_project(self, *args):
        if not self.selected or self.busy:
            return
        body = {
            "expected_project_revision": self.selected["project_revision"],
            "name": dpg.get_value("pm_name"),
            "description": dpg.get_value("pm_description"),
            "archived": dpg.get_value("pm_archived"),
            "folder_id": self.folder_choices.get(dpg.get_value("pm_folder")),
        }
        client, pid, key = self.app.client, self.selected["id"], uid()
        self.run(lambda: client.request("PATCH", f"/projects/{pid}", body, key=key), lambda _: self.refresh())

    def open_selected(self, *args):
        if self.selected and not self.busy:
            pid = self.selected["id"]
            dpg.hide_item("project_manager")
            self.app.guard(lambda: self.app.load_project(pid))

    def new_project(self, *args):
        if self.busy:
            return
        dpg.hide_item("project_manager")
        self.app.exports.show_after_modal_closes("new_project")

    def select_folder(self, *args):
        fid = self.folder_choices.get(dpg.get_value("pm_folder_edit"))
        if fid:
            folder = self.folders[fid]
            dpg.set_value("pm_folder_name", folder["name"])
            dpg.set_value(
                "pm_parent",
                next(label for label, ident in self.folder_choices.items() if ident == folder["parent_id"]),
            )

    def save_folder(self, create, delete=False):
        fid = None if create else self.folder_choices.get(dpg.get_value("pm_folder_edit"))
        if not create and not fid:
            return
        body = {
            "name": dpg.get_value("pm_folder_name"),
            "parent_id": self.folder_choices.get(dpg.get_value("pm_parent")),
            "expected_revision": self.folders[fid]["revision"] if fid else 0,
            "delete": delete,
        }
        client, key = self.app.client, uid()
        self.run(
            lambda: client.request(
                "PUT" if fid else "POST", "/project-folders" + (f"/{fid}" if fid else ""), body, key=key
            ),
            lambda _: self.refresh(),
        )

    def save_template(self, *args):
        if self.selected:
            client, pid, key = self.app.client, self.selected["id"], uid()
            body = {"name": dpg.get_value("pm_template_name")}
            self.run(
                lambda: client.request("POST", f"/projects/{pid}/class-templates", body, key=key),
                lambda _: self.refresh(),
            )

    def new_from_template(self, *args):
        template = self.templates.get(dpg.get_value("pm_template"))
        if template and not self.busy:
            dpg.set_value("project_classes", json.dumps(template["initial_classes"], ensure_ascii=False))
            dpg.set_value("project_task", template["task_type"])
            self.new_project()

    def load_versions(self, *args):
        if self.selected:
            client, pid = self.app.client, self.selected["id"]
            self.run(
                lambda: client.request("GET", f"/projects/{pid}/versions"),
                lambda result: dpg.set_value(
                    "pm_versions",
                    version_report(result),
                ),
            )

    def invalidate_preview(self, *args):
        self.preview_generation += 1
        self.preview = None
        self.preview_keys = {}
        dpg.configure_item("pm_remap_apply", enabled=False)

    def load_images(self, *args):
        if not self.selected:
            return
        client, pid = self.app.client, self.selected["id"]

        def done(items):
            self.image_items = items
            self.filter_images()

        self.run(lambda: client.list_all(f"/projects/{pid}/images"), done)

    def filter_images(self):
        search = dpg.get_value("pm_image_search").casefold()
        matching = [i for i in self.image_items if search in i["display_filename"].casefold()]
        self.image_choices = {f"{i['display_filename']} [{i['id']}]": i["id"] for i in matching[:200]}
        dpg.configure_item("pm_image_picker", items=list(self.image_choices))
        dpg.set_value("pm_image_picker", next(iter(self.image_choices), ""))
        if len(matching) > 200:
            self.message("Showing the first 200 matching images. Narrow the filename search.")

    def add_image(self, *args):
        if self.busy:
            return
        iid = self.image_choices.get(dpg.get_value("pm_image_picker"))
        if iid:
            ids = dpg.get_value("pm_remap_images").split()
            dpg.set_value("pm_remap_images", "\n".join(dict.fromkeys(ids + [iid])))
            self.invalidate_preview()

    def clear_images(self, *args):
        if not self.busy:
            dpg.set_value("pm_remap_images", "")
            self.invalidate_preview()

    def preview_remap(self, *args):
        if not self.selected or self.busy:
            return
        try:
            names = {e["display_name"]: e["class_id"] for e in self.selected["schema"]["entries"]}
            mapping = {}
            for line in dpg.get_value("pm_remap_mapping").splitlines():
                if not line.strip():
                    continue
                source, sep, target = line.partition("=")
                if (
                    not sep
                    or source.strip() not in names
                    or target.strip() not in names
                    or names[source.strip()] in mapping
                ):
                    raise Problem("INVALID_MAPPING", "Use unique source names and exact destination names.")
                mapping[names[source.strip()]] = names[target.strip()]
            body = {"image_ids": dpg.get_value("pm_remap_images").split(), "mapping": mapping}
            client, pid = self.app.client, self.selected["id"]
            generation = self.preview_generation

            def done(result):
                if generation != self.preview_generation:
                    self.message("Selection changed. Run Preview again.")
                    return
                self.preview = result
                self.preview_keys = {i["image_id"]: uid() for i in result["items"]}
                dpg.set_value("pm_remap_report", json.dumps(result, ensure_ascii=False, indent=2))
                dpg.configure_item("pm_remap_apply", enabled=bool(result["changed_images"]))

            self.run(lambda: client.request("POST", f"/projects/{pid}/remap-preview", body), done)
        except Problem as exc:
            self.message(exc.message)

    def apply_remap(self, *args):
        if not self.preview or self.busy:
            return
        preview, keys, client = self.preview, dict(self.preview_keys), self.app.client
        current_id = self.app.image["id"] if self.app.image else None
        current_claim = self.app.claim

        def work():
            results = []
            for item in preview["items"]:
                if not item["changed_labels"]:
                    continue
                iid, lease, acquired = item["image_id"], None, False
                try:
                    if iid == current_id and current_claim:
                        lease = current_claim
                    else:
                        lease = client.request(
                            "POST",
                            f"/images/{iid}/claim",
                            {"mode": "edit", "client_instance_id": client.instance},
                            key=uid(),
                        )
                        acquired = True
                    body = {
                        k: item[k]
                        for k in (
                            "expected_revision",
                            "expected_state_revision",
                            "annotation_sha256",
                            "class_schema_id",
                        )
                    }
                    saved = client.request(
                        "POST",
                        f"/images/{iid}/remap",
                        body | {"mapping": preview["mapping"]},
                        claim=lease,
                        key=keys[iid],
                    )
                    results.append(
                        {"image_id": iid, "filename": item["filename"], "saved_revision": saved["revision"]}
                    )
                except Problem as exc:
                    results.append(
                        {
                            "image_id": iid,
                            "filename": item["filename"],
                            "error": exc.code,
                            "message": exc.message,
                        }
                    )
                finally:
                    if acquired:
                        try:
                            client.request("DELETE", f"/images/{iid}/claim", claim=lease)
                        except Problem:
                            pass
            return results

        def done(results):
            dpg.set_value("pm_remap_report", json.dumps(results, ensure_ascii=False, indent=2))
            self.message(
                "Remap finished. Inspect per-image results. Retry uses the same request keys; changed sources require a new preview."
            )
            if current_id and any(r["image_id"] == current_id and "saved_revision" in r for r in results):
                self.app.open_image(current_id)

        self.run(work, done)


def version_report(result):
    working = result["working"]
    lines = [
        "Working data (editable)",
        f"Images: {working['images']} | Project revision: {working['project_revision']}",
        f"Last saved change: {working['last_modified'] or 'None'}",
        "",
        "Class schemas (immutable)",
    ]
    for schema in result["schemas"]:
        lines += [
            f"Schema {schema['number']} | {schema['created_at']}",
            f"  ID: {schema['id']}",
            f"  SHA256: {schema['sha256']}",
        ]
    lines += ["", "Export snapshots — Unreviewed"]
    for job in result["exports"]:
        lines += [
            f"{job['created_at']} | {job['state']} | {job['id']}",
            f"  Snapshot: {job['snapshot_sha256']}",
            f"  Format: {job['format_version']} | Schema: {job['schema_id']}",
            f"  Validation: {job['options']['validation_percent']}% | Test: {job['options']['test_percent']}% | Seed: {job['options']['seed']}",
            "  Model mapping: " + json.dumps(job["options"].get("class_mapping"), ensure_ascii=False),
        ]
        if job["result"]:
            lines.append(
                f"  Included: {job['result']['included']} | Excluded: {job['result']['excluded_count']}"
            )
        if job["error"]:
            lines.append("  " + job["error"]["message"])
    lines += ["", "Approved releases", result["release_status"]]
    return "\n".join(lines)


def load_import_model(app):
    try:
        path = Path(dpg.get_value("yolo_model_path"))
        if path.stat().st_size > 1024 * 1024:
            raise Problem("INVALID_MODEL_NAMES", "Model YAML exceeds 1 MiB.")
        names = model_names(path.read_text(encoding="utf-8-sig"))
        dpg.set_value("yolo_mapping", "\n".join(f"{i}={name}" for i, name in sorted(names.items())))
        app.message("Model indices loaded. Compare with project names, then run Preview before importing.")
    except (OSError, UnicodeError, Problem) as exc:
        app.error(exc)

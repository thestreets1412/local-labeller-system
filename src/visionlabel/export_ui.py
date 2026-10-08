"""Desktop working export: prepare a saved snapshot, inspect counts, save locally."""

import csv
import json
import time
from pathlib import Path
from urllib.parse import urlencode

import dearpygui.dearpygui as dpg

from .class_mapping import model_names, parse_mapping
from .domain import Problem, uid
from .working_export import ExportRequest


def failure_report(exc):
    """Human-readable details; decimal strings must survive unchanged."""
    if not isinstance(exc, Problem):
        return f"Export failed: {exc}"
    lines = [exc.message]
    details = exc.details
    if details.get("job_id"):
        lines.append(f"Job: {details['job_id']}")
    if details.get("snapshot_sha256"):
        lines.append(f"Snapshot: {details['snapshot_sha256']}")
    issues = details.get("issues", [])
    if len(issues) > 200:
        lines.append("Showing the first 200 errors. Save the JSON report for all errors.")
    for number, issue in enumerate(issues[:200], 1):
        lines.extend(
            [
                "",
                f"Error {number} | Image: {issue['filename']} ({issue['image_id']})",
                f"Saved revision: {issue['annotation_revision']} | Size: {issue['width']} x {issue['height']}",
                f"Box/shape {issue['shape_number']}: {issue['shape_id']}",
                f"Class: {issue['export_index']} = {issue['class_name']}",
                "Failed checks: " + ", ".join(issue["failed_checks"]),
            ]
        )
        for key in ("source", "quantized", "edges", "source_points", "quantized_points"):
            if key in issue:
                lines.append(f"{key}: {json.dumps(issue[key], ensure_ascii=False)}")
    return "\n".join(lines)


class ExportPanel:
    def __init__(self, desktop):
        self.app = desktop
        self.busy = False
        self.prepared = None
        self.project_id = None
        self.request_key = None
        self.request_body = None
        self.failed_report = None
        self.report_client = None
        self.history = {}
        self.history_cursor = None

    def build(self):
        with dpg.file_dialog(
            tag="export_folder_picker",
            directory_selector=True,
            modal=True,
            show=False,
            width=750,
            height=450,
            callback=self.choose_folder,
            cancel_callback=self.cancel_folder,
        ):
            pass
        with dpg.window(
            tag="export_dialog",
            label="Export YOLO training dataset",
            modal=True,
            show=False,
            width=820,
            height=650,
            pos=(180, 60),
        ):
            dpg.add_text(
                "Export saved labels from this project, including unreviewed predictions.\nUnlabeled images are excluded. Review predictions and save edits first.",
                wrap=760,
            )
            dpg.add_text("", tag="export_project")
            with dpg.collapsing_header(label="Model class mapping (optional)"):
                dpg.add_text(
                    "Empty uses the project schema. Otherwise include every class: index=project class name.",
                    wrap=740,
                )
                dpg.add_text(
                    "Classification folder consumers number observed classes consecutively; check consumer_order in class_mapping.json.",
                    wrap=740,
                )
                dpg.add_input_text(
                    tag="export_mapping", multiline=True, height=95, width=700, callback=self.invalidate
                )
                dpg.add_input_text(label="Local model data.yaml", tag="export_model_path", width=550)
                dpg.add_button(label="Load model names / compare", callback=self.load_model)
            with dpg.group(horizontal=True):
                dpg.add_button(
                    label="Previous failures",
                    tag="export_history_refresh",
                    callback=lambda: self.load_history(),
                )
                dpg.add_button(
                    label="Older",
                    tag="export_history_older",
                    enabled=False,
                    callback=lambda: self.load_history(True),
                )
            dpg.add_combo([], tag="export_history", width=700, label="Failed job")
            dpg.add_button(label="Load selected report", tag="export_history_load", callback=self.load_report)
            with dpg.group(horizontal=True):
                dpg.add_input_int(
                    label="Validation %",
                    tag="export_val",
                    default_value=20,
                    width=95,
                    callback=self.invalidate,
                )
                dpg.add_input_int(
                    label="Test %", tag="export_test", default_value=10, width=95, callback=self.invalidate
                )
                dpg.add_input_int(
                    label="Seed", tag="export_seed", default_value=42, width=120, callback=self.invalidate
                )
            dpg.add_text(
                "Train receives the remainder. Validation must be at least 1%; test can be 0%.\nGroups, class coverage and rounding may change actual counts.",
                wrap=760,
            )
            dpg.add_button(
                label="1. Prepare export / retry", tag="export_prepare", callback=lambda: self.prepare()
            )
            dpg.add_input_text(tag="export_report", multiline=True, readonly=True, width=-1, height=230)
            with dpg.group(horizontal=True):
                dpg.add_input_int(
                    label="Error number",
                    tag="export_issue_number",
                    default_value=1,
                    min_value=1,
                    min_clamped=True,
                    width=100,
                )
                dpg.add_button(
                    label="Open image / select shape",
                    tag="export_open_issue",
                    enabled=False,
                    callback=self.open_issue,
                )
                dpg.add_combo(["JSON", "CSV"], default_value="JSON", tag="export_report_format", width=80)
            dpg.add_button(
                label="Save error report to parent folder",
                tag="export_save_report",
                enabled=False,
                callback=self.save_error_report,
            )
            with dpg.group(horizontal=True):
                dpg.add_button(label="Browse parent folder...", callback=self.browse_folder)
                dpg.add_input_text(
                    label="New folder name", tag="export_name", default_value="yolo-dataset", width=230
                )
            dpg.add_input_text(
                label="Parent folder", tag="export_parent", default_value=str(Path.home()), width=600
            )
            dpg.add_text(
                "A new folder will be created here on this computer. Existing folders are never overwritten.",
                wrap=760,
            )
            dpg.add_button(
                label="2. Save dataset to folder",
                tag="export_save",
                enabled=False,
                callback=lambda: self.save(),
            )
            dpg.add_text("", tag="export_status", wrap=760)
            dpg.add_button(label="Close", callback=lambda: dpg.hide_item("export_dialog"))

    def browse_folder(self, *args):
        # Only one modal can own input: suspend Export until the picker returns.
        parent = Path(dpg.get_value("export_parent"))
        if parent.is_dir():
            dpg.configure_item("export_folder_picker", default_path=str(parent))
        dpg.hide_item("export_dialog")
        self.show_after_modal_closes("export_folder_picker")

    @staticmethod
    def show_after_modal_closes(tag):
        # ImGui must render a frame without the old popup before opening another.
        dpg.set_frame_callback(dpg.get_frame_count() + 2, lambda: dpg.show_item(tag))

    def cancel_folder(self, *args):
        dpg.hide_item("export_folder_picker")
        self.show_after_modal_closes("export_dialog")

    def choose_folder(self, sender, data):
        dpg.set_value("export_parent", data["file_path_name"])
        self.cancel_folder()

    def invalidate(self, *args):
        if not self.busy:
            self.prepared = None
            self.request_key = None
            self.failed_report = None
            self.report_client = None
            self.clear_history()
            dpg.configure_item("export_open_issue", enabled=False)
            dpg.configure_item("export_save_report", enabled=False)
            dpg.configure_item("export_save", enabled=False)
            dpg.set_value("export_status", "Settings changed. Prepare a new export.")

    def set_busy(self, value):
        self.busy = value
        for tag in ("export_val", "export_test", "export_seed", "export_prepare"):
            dpg.configure_item(tag, enabled=not value)
        for tag in ("export_history_refresh", "export_history_load"):
            dpg.configure_item(tag, enabled=not value)
        dpg.configure_item("export_history_older", enabled=not value and bool(self.history_cursor))
        dpg.configure_item("export_open_issue", enabled=not value and self.failed_report is not None)
        dpg.configure_item("export_save", enabled=not value and self.prepared is not None)

    def open(self):
        if not self.app.project or not self.app.project.get("can_manage_members"):
            self.app.message("Select a project where you are an administrator or maintainer.")
            return
        if self.busy and self.project_id != self.app.project["id"]:
            self.app.message("Wait for the export of the previous project to finish.")
            return
        if (self.prepared and self.prepared["client"] is not self.app.client) or (
            self.report_client and self.report_client is not self.app.client
        ):
            self.invalidate()
            self.clear_history()
        if self.app.saving or self.app.editor.dirty or getattr(self.app.canvas, "draft", None):
            self.app.message("Finish polygons and save your changes before opening Export YOLO.")
            return
        if not self.busy and self.project_id != self.app.project["id"]:
            self.project_id = self.app.project["id"]
            self.invalidate()
            self.clear_history()
            dpg.set_value("export_report", "")
            dpg.set_value("export_mapping", "")
        dpg.set_value("export_project", f"{self.app.project['name']} / {self.app.project['task_type']}")
        dpg.show_item("export_dialog")

    def failure(self, exc):
        self.set_busy(False)
        dpg.set_value("export_status", exc.message if isinstance(exc, Problem) else f"Export failed: {exc}")
        dpg.set_value("export_report", failure_report(exc))
        self.failed_report = (
            {"code": exc.code, "message": exc.message, "details": exc.details}
            if isinstance(exc, Problem) and exc.details.get("issues")
            else None
        )
        dpg.configure_item("export_save_report", enabled=self.failed_report is not None)
        dpg.configure_item("export_open_issue", enabled=self.failed_report is not None)
        dpg.set_value("export_issue_number", 1)

    def clear_history(self):
        self.history = {}
        self.history_cursor = None
        dpg.configure_item("export_history", items=[])
        dpg.set_value("export_history", "")
        dpg.configure_item("export_history_older", enabled=False)

    def load_history(self, older=False):
        if self.busy or not self.app.project or self.app.project["id"] != self.project_id:
            return
        client, pid = self.app.client, self.project_id
        cursor = self.history_cursor if older else None
        self.set_busy(True)

        def done(result):
            self.set_busy(False)
            if client is not self.app.client or not self.app.project or self.app.project["id"] != pid:
                self.clear_history()
                return
            self.history = {f"{i['created_at']} | {i['id']}": i["id"] for i in result["items"]}
            self.report_client = client
            self.history_cursor = result["next_cursor"]
            dpg.configure_item("export_history", items=list(self.history))
            dpg.set_value("export_history", next(iter(self.history), ""))
            dpg.configure_item("export_history_older", enabled=bool(self.history_cursor))
            dpg.set_value(
                "export_status",
                f"{len(self.history)} failed jobs on this page. Select a job and load its report.",
            )

        self.app.submit(
            lambda: client.request(
                "GET",
                f"/projects/{pid}/export-failures" + ("?" + urlencode({"cursor": cursor}) if cursor else ""),
            ),
            done,
            self.failure,
        )

    def load_report(self, *args):
        if (
            self.busy
            or self.report_client is not self.app.client
            or not self.app.project
            or self.app.project["id"] != self.project_id
        ):
            return
        job_id = self.history.get(dpg.get_value("export_history"))
        if not job_id:
            return
        client, pid = self.app.client, self.project_id
        self.set_busy(True)

        def done(job):
            self.set_busy(False)
            if client is not self.app.client or not self.app.project or self.app.project["id"] != pid:
                return
            self.prepared = None
            self.request_key = None
            self.report_client = client
            error = job["error"]
            self.failure(
                Problem(error["code"], error["message"], **(error.get("details", {}) | {"job_id": job_id}))
            )

        self.app.submit(lambda: client.request("GET", f"/jobs/{job_id}"), done, self.failure)

    def open_issue(self, *args):
        if self.busy or not self.failed_report:
            return
        if (
            self.report_client is not self.app.client
            or not self.app.project
            or self.app.project["id"] != self.project_id
        ):
            dpg.set_value("export_status", "Project or connection changed. Load the report again.")
            return
        issues = self.failed_report["details"]["issues"]
        number = dpg.get_value("export_issue_number")
        if not 1 <= number <= len(issues):
            dpg.set_value("export_status", f"Choose an error number from 1 to {len(issues)}.")
            return
        issue = issues[number - 1]
        client, pid = self.app.client, self.project_id

        def loaded():
            head = self.app.head
            changed = (
                head["revision"] != issue["annotation_revision"]
                or head["annotation_sha256"] != issue["annotation_sha256"]
            )
            exists = any(s["id"] == issue["shape_id"] for s in self.app.editor.content["shapes"])
            if exists and not self.app.blocked:
                self.app.select_shape(issue["shape_id"])
            message = (
                f"Export report revision {issue['annotation_revision']}; loaded revision {head['revision']}. "
            )
            if changed:
                message += (
                    "Saved annotation changed since this report. Prepare a new export after inspection. "
                )
            if self.app.blocked:
                message += "Resolve the recovery draft before selecting or editing the reported shape. "
            elif not exists:
                message += "The reported shape no longer exists. "
            else:
                message += "Reported shape selected. "
            if not self.app.claim:
                message += "Read-only: no editing lease is available."
            self.app.message(message)

        def navigate():
            if client is self.app.client and self.app.project and self.app.project["id"] == pid:
                self.app.open_image(issue["image_id"], on_loaded=loaded)

        dpg.hide_item("export_dialog")
        # Let the export modal close before a dirty-navigation/recovery modal opens.
        dpg.set_frame_callback(dpg.get_frame_count() + 2, lambda: self.app.guard(navigate))

    def save_error_report(self, *args):
        if self.failed_report is None:
            return
        kind = dpg.get_value("export_report_format") or "JSON"
        path = Path(dpg.get_value("export_parent")) / f"export-errors-{uid()}.{kind.lower()}"
        try:
            # A report is client-local and must not replace any user file.
            with path.open("x", encoding="utf-8-sig" if kind == "CSV" else "utf-8", newline="") as stream:
                if kind == "CSV":
                    details = self.failed_report["details"]
                    fields = [
                        "job_id",
                        "snapshot_sha256",
                        "filename",
                        "image_id",
                        "annotation_revision",
                        "annotation_sha256",
                        "shape_number",
                        "shape_id",
                        "class_name",
                        "export_index",
                        "width",
                        "height",
                        "failed_checks",
                        "source",
                        "quantized",
                        "edges",
                        "source_points",
                        "quantized_points",
                    ]
                    writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
                    writer.writeheader()
                    for issue in details["issues"]:
                        row = {
                            "job_id": details.get("job_id", ""),
                            "snapshot_sha256": details.get("snapshot_sha256", ""),
                            **issue,
                        }
                        for key, value in row.items():
                            if isinstance(value, (dict, list)):
                                row[key] = json.dumps(value, ensure_ascii=False)
                            elif isinstance(value, str) and value.startswith(
                                ("=", "+", "-", "@", "\t", "\r", "\n")
                            ):
                                row[key] = "'" + value
                        writer.writerow(row)
                else:
                    json.dump(self.failed_report, stream, ensure_ascii=False, indent=2)
        except OSError as exc:
            dpg.set_value("export_status", f"Could not save error report: {exc}")
            return
        dpg.set_value("export_status", f"Error report saved: {path}")

    def prepare(self):
        if self.busy or not self.app.project:
            return
        try:
            mapping_text = dpg.get_value("export_mapping") or ""
            mapping = (
                parse_mapping(mapping_text, self.app.project["schema"]["entries"], complete=True)
                if mapping_text.strip()
                else None
            )
            body = ExportRequest(
                class_mapping={cid: index for index, cid in mapping.items()} if mapping is not None else None,
                validation_percent=dpg.get_value("export_val"),
                test_percent=dpg.get_value("export_test"),
                seed=dpg.get_value("export_seed"),
            ).model_dump()
        except Problem as exc:
            self.failure(exc)
            return
        except ValueError:
            dpg.set_value(
                "export_status",
                "Use whole percentages: validation 1-99, test 0-98, sum below 100; seed 0-2147483647.",
            )
            return
        self.prepared = None
        self.failed_report = None
        self.report_client = self.app.client
        dpg.configure_item("export_save_report", enabled=False)
        if body != self.request_body or self.request_key is None:
            self.request_body, self.request_key = body, uid()
        key, project_id, client = self.request_key, self.project_id, self.app.client
        names = {e["class_id"]: e["display_name"] for e in self.app.project["schema"]["entries"]}
        names["__empty__"] = "Verified empty"
        self.set_busy(True)
        dpg.set_value("export_report", "")
        dpg.set_value(
            "export_status", "Preparing saved snapshot and verifying files. Large datasets may take time..."
        )

        def work():
            job_id = client.request("POST", f"/projects/{project_id}/working-exports", body, key=key)[
                "job_id"
            ]
            while not self.app.exit_requested:
                job = client.request("GET", f"/jobs/{job_id}")
                if job["state"] == "failed":
                    error = job["error"]
                    raise Problem(
                        error["code"],
                        error["message"],
                        **(error.get("details", {}) | {"job_id": job_id}),
                    )
                if job["state"] == "succeeded":
                    return {"job_id": job_id, "result": job["result"], "client": client}
                time.sleep(0.5)
            raise Problem("CANCELLED", "Desktop closed. Prepare again on the next run.")

        def done(prepared):
            self.prepared = prepared
            self.request_key = None
            self.set_busy(False)
            result = prepared["result"]
            counts = result["split"]["actual_counts"]
            split = result["split"]
            lines = [
                f"Included: {result['included']} images    Excluded: {result['excluded_count']}",
                "",
                "Set        Images    Requested %    Actual %",
            ]
            for part in ("train", "val", "test"):
                lines.append(
                    f"{part:8}   {counts[part]:6}    {split['requested_percent'][part]:8.0f}    {split['actual_percent'][part]:8.2f}"
                )
            lines += ["", "Class image counts (train / val / test):"]
            for cls, per_set in split["class_image_counts"].items():
                lines.append(
                    f"{names.get(cls, cls)}: {per_set['train']} / {per_set['val']} / {per_set['test']}"
                )
            lines += ["", split["note"], "", "Excluded images (first 200; full list in manifest.json):"]
            lines.extend(f"{item['filename']}: {item['reason']}" for item in result["excluded"][:200])
            dpg.set_value("export_report", "\n".join(lines))
            dpg.set_value(
                "export_status",
                f"Ready: train {counts['train']}, val {counts['val']}, test {counts['test']}. Excluded: {result['excluded_count']}. Check counts, then save to a new folder.",
            )

        def failed(exc):
            if not isinstance(exc, Problem) or exc.code != "DISCONNECTED":
                self.request_key = None
            self.failure(exc)

        self.app.submit(work, done, failed)

    def load_model(self, *args):
        if self.busy:
            return
        try:
            path = Path(dpg.get_value("export_model_path"))
            if path.stat().st_size > 1024 * 1024:
                raise Problem("INVALID_MODEL_NAMES", "Model YAML exceeds 1 MiB.")
            names = model_names(path.read_text(encoding="utf-8-sig"))
            text = "\n".join(f"{i}={name}" for i, name in sorted(names.items()))
            dpg.set_value("export_mapping", text)
            self.invalidate()
            parse_mapping(text, self.app.project["schema"]["entries"], complete=True)
            dpg.set_value(
                "export_status",
                "Model names loaded. Inspect the index-to-class mapping before preparing export.",
            )
        except (OSError, UnicodeError, Problem) as exc:
            self.failure(exc)

    def save(self):
        if self.busy or self.prepared is None:
            return
        name = dpg.get_value("export_name").strip()
        if (
            not name
            or name in (".", "..")
            or any(c in name for c in '/\\:*?"<>|')
            or name.endswith((".", " "))
        ):
            self.failure(Problem("INVALID_DESTINATION", "Enter a single new folder name."))
            return
        destination = Path(dpg.get_value("export_parent")) / name
        prepared = self.prepared
        self.set_busy(True)
        dpg.set_value("export_status", "Downloading and verifying dataset files...")

        def done(path):
            self.set_busy(False)
            dpg.set_value(
                "export_status",
                f"Export complete: {path}\nSee TRAINING.txt. Detection/segmentation: data.local.yaml. Classification: this dataset folder.",
            )

        self.app.submit(
            lambda: prepared["client"].download_export(prepared["job_id"], destination, prepared["result"]),
            done,
            self.failure,
        )

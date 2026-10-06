"""Desktop working export: prepare a saved snapshot, inspect counts, save locally."""

import time
from pathlib import Path

import dearpygui.dearpygui as dpg

from .domain import Problem, uid
from .working_export import ExportRequest


class ExportPanel:
    def __init__(self, desktop):
        self.app = desktop
        self.busy = False
        self.prepared = None
        self.project_id = None
        self.request_key = None
        self.request_body = None

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
                dpg.add_button(
                    label="Browse parent folder...", callback=self.browse_folder
                )
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
        dpg.show_item("export_folder_picker")

    def cancel_folder(self, *args):
        dpg.hide_item("export_folder_picker")
        dpg.show_item("export_dialog")

    def choose_folder(self, sender, data):
        dpg.set_value("export_parent", data["file_path_name"])
        self.cancel_folder()

    def invalidate(self, *args):
        if not self.busy:
            self.prepared = None
            self.request_key = None
            dpg.configure_item("export_save", enabled=False)
            dpg.set_value("export_status", "Settings changed. Prepare a new export.")

    def set_busy(self, value):
        self.busy = value
        for tag in ("export_val", "export_test", "export_seed", "export_prepare"):
            dpg.configure_item(tag, enabled=not value)
        dpg.configure_item("export_save", enabled=not value and self.prepared is not None)

    def open(self):
        if not self.app.project or not self.app.project.get("can_manage_members"):
            self.app.message("Select a project where you are an administrator or maintainer.")
            return
        if self.busy and self.project_id != self.app.project["id"]:
            self.app.message("Wait for the export of the previous project to finish.")
            return
        if self.prepared and self.prepared["client"] is not self.app.client:
            self.invalidate()
        if self.app.saving or self.app.editor.dirty or getattr(self.app.canvas, "draft", None):
            self.app.message("Finish polygons and save your changes before opening Export YOLO.")
            return
        if not self.busy and self.project_id != self.app.project["id"]:
            self.project_id = self.app.project["id"]
            self.invalidate()
            dpg.set_value("export_report", "")
        dpg.set_value("export_project", f"{self.app.project['name']} / {self.app.project['task_type']}")
        dpg.show_item("export_dialog")

    def failure(self, exc):
        self.set_busy(False)
        dpg.set_value("export_status", exc.message if isinstance(exc, Problem) else f"Export failed: {exc}")

    def prepare(self):
        if self.busy or not self.app.project:
            return
        try:
            body = ExportRequest(
                validation_percent=dpg.get_value("export_val"),
                test_percent=dpg.get_value("export_test"),
                seed=dpg.get_value("export_seed"),
            ).model_dump()
        except ValueError:
            dpg.set_value(
                "export_status",
                "Use whole percentages: validation 1-99, test 0-98, sum below 100; seed 0-2147483647.",
            )
            return
        self.prepared = None
        if body != self.request_body or self.request_key is None:
            self.request_body, self.request_key = body, uid()
        key, project_id, client = self.request_key, self.project_id, self.app.client
        names = {e["class_id"]: e["display_name"] for e in self.app.project["schema"]["entries"]}
        names["__empty__"] = "Verified empty"
        self.set_busy(True)
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
                    raise Problem(error["code"], error["message"])
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

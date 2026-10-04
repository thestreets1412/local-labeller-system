"""Read-only statistics for persisted working annotations."""

import dearpygui.dearpygui as dpg

from .domain import Problem


class StatisticsPanel:
    def __init__(self, desktop):
        self.app = desktop
        self.busy = False
        self.result = None

    def build(self):
        with dpg.window(
            label="Working dataset - Statistics / QC",
            tag="statistics",
            modal=True,
            show=False,
            width=850,
            height=650,
            pos=(240, 90),
        ):
            dpg.add_text(
                "Saved annotations only. Save your changes, then Refresh to update this report.", wrap=790
            )
            dpg.add_button(label="Refresh", callback=lambda: self.refresh())
            dpg.add_text("", tag="statistics_status", wrap=790)
            with dpg.child_window(tag="statistics_body", height=-45):
                pass
            dpg.add_button(label="Close", callback=lambda: dpg.hide_item("statistics"))

    def open(self):
        if not self.app.project:
            self.app.message("Choose a project before opening statistics.")
            return
        dpg.show_item("statistics")
        self.refresh()

    def refresh(self):
        if self.busy or not self.app.project:
            return
        self.busy = True
        project_id, client = self.app.project["id"], self.app.client
        dpg.set_value("statistics_status", "Reading saved annotations...")

        def failure(exc):
            self.busy = False
            dpg.set_value(
                "statistics_status", exc.message if isinstance(exc, Problem) else "Could not load statistics."
            )

        def done(result):
            self.busy = False
            if not self.app.project or self.app.project["id"] != project_id:
                dpg.set_value("statistics_status", "Project changed. Refresh to load the current project.")
                return
            self.result = result
            dpg.set_value(
                "statistics_status",
                f"{self.app.project['name']} / {result['total_images']} images / {result['verified_empty_images']} verified empty / {result['approved_images']} approved\nUpdated {result['generated_at']}",
            )
            dpg.delete_item("statistics_body", children_only=True)
            with dpg.table(
                parent="statistics_body",
                header_row=True,
                borders_innerH=True,
                policy=dpg.mvTable_SizingStretchProp,
            ):
                for label in ("Class", "Images", "Objects"):
                    dpg.add_table_column(label=label)
                for cls in result["classes"]:
                    with dpg.table_row():
                        dpg.add_text(cls["display_name"])
                        dpg.add_text(str(cls["image_count"]))
                        dpg.add_text(str(cls["object_count"]))
            for title, key in (
                ("Statuses", "status_counts"),
                ("Image formats", "formats"),
                ("Resolutions", "resolutions"),
                ("Groups", "groups"),
            ):
                dpg.add_text(
                    title + ": " + ", ".join(f"{k}: {v}" for k, v in result[key].items()),
                    parent="statistics_body",
                    wrap=755,
                )
            counts = result["class_imbalance"]
            dpg.add_text(
                f"Class image counts: min {counts['min_image_count']}, max {counts['max_image_count']}. {len(counts['classes_without_images'])} classes have no saved images.",
                parent="statistics_body",
                wrap=755,
            )
            warnings = result["warnings"]
            dpg.add_separator(parent="statistics_body")
            dpg.add_text(
                f"QC warnings: {len(warnings)} (showing first {min(200, len(warnings))})",
                parent="statistics_body",
            )
            for warning in warnings[:200]:
                dpg.add_text(
                    f"{warning['filename']} / {warning['code']}: {warning['message']}",
                    parent="statistics_body",
                    wrap=755,
                )

        self.app.submit(lambda: client.request("GET", f"/projects/{project_id}/statistics"), done, failure)

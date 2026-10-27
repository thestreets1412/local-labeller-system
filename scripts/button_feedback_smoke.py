"""Rendered feedback/scroll/shortcut smoke using local guards, without a service.

This exercises real Dear PyGui widgets through callbacks, not physical mouse/DPI acceptance.
"""

import argparse
import json
from pathlib import Path

import dearpygui.dearpygui as dpg

from visionlabel.desktop import Desktop
from visionlabel.domain import Problem


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    app = Desktop("http://127.0.0.1:9")
    checks = []
    try:
        app.build()

        def frames(count=5):
            for _ in range(count):
                dpg.run_callbacks(dpg.get_callback_queue())
                app.tick()
                dpg.render_dearpygui_frame()

        def show(window):
            for tag in (
                "connection",
                "new_project",
                "project_manager",
                "dataset_manager",
                "checkpoint_browser",
                "export_dialog",
                "review_reject",
                "review_settings",
                "team",
            ):
                dpg.hide_item(tag)
            frames()
            dpg.show_item(window)
            frames()

        def check(window, status, expected, name):
            frames()
            assert dpg.is_item_shown(window)
            assert dpg.is_item_visible(status), (name, "feedback hidden")
            assert expected in dpg.get_value(status), (name, dpg.get_value(status))
            wx, wy = dpg.get_item_pos(window)
            ww, wh = dpg.get_item_rect_size(window)
            tx, ty = dpg.get_item_rect_min(status)
            tw, th = dpg.get_item_rect_size(status)
            assert wx <= tx < wx + ww and wy <= ty < ty + th <= wy + wh, (name, "outside window")
            checks.append(name)

        show("connection")
        for tag in ("server", "username", "password", "connection_connect", "connection_cancel"):
            assert dpg.is_item_visible(tag), (tag, "login control is not visible")
            _, y = dpg.get_item_rect_min(tag)
            _, height = dpg.get_item_rect_size(tag)
            _, body_y = dpg.get_item_pos("connection")
            _, body_height = dpg.get_item_rect_size("connection")
            assert body_y <= y and y + height <= body_y + body_height, (tag, "login control is clipped")
        dpg.output_frame_buffer(str(args.output / "login.png"))
        frames()
        checks.append("login fields and buttons fit without scrolling")
        app.busy = True
        app.connect()
        check("connection", "connection_status", "Wait", "connection busy visible")
        app.busy = False
        app.error(Problem("DISCONNECTED", "Connection lost.", 503))
        check("connection", "connection_status", "unknown", "connection error visible")

        show("new_project")
        for tag in ("project_name", "project_slug", "project_task", "project_classes"):
            assert dpg.is_item_visible(tag), (tag, "project field is not visible")
            _, y = dpg.get_item_rect_min(tag)
            _, height = dpg.get_item_rect_size(tag)
            _, body_y = dpg.get_item_pos("new_project")
            _, body_height = dpg.get_item_rect_size("new_project")
            assert body_y <= y and y + height <= body_y + body_height, (tag, "project field is clipped")
        checks.append("project fields fit without scrolling")

        show("review_reject")
        dpg.set_value("review_reason", "Other")
        dpg.set_value("review_comment", "")
        app.review.reject()
        check("review_reject", "review_reject_status", "Enter Details", "reject reason visible")

        show("project_manager")
        app.project_manager.datasets.open()
        check("project_manager", "pm_status", "Select a project", "classes missing selection keeps manager")
        app.project_manager.selected = {"id": "synthetic", "can_manage_members": False}
        app.project_manager.datasets.open()
        check("project_manager", "pm_status", "Ask a maintainer", "classes role explains next step")

        show("dataset_manager")
        dpg.configure_item("dataset_manager", width=700, height=500)
        app.project_manager.busy = True
        app.project_manager.datasets.prepare("checkpoint")
        check("dataset_manager", "ds_status", "Wait", "dataset busy visible at 700px")
        before = dpg.get_item_rect_min("ds_status")
        dpg.set_y_scroll("dataset_manager_feedback_body", 10000)
        check("dataset_manager", "ds_status", "Wait", "dataset feedback survives content scroll")
        assert dpg.get_item_rect_min("ds_status") == before
        dpg.output_frame_buffer(str(args.output / "dataset-feedback.png"))
        frames()

        show("checkpoint_browser")
        app.project_manager.datasets.view_image()
        check("checkpoint_browser", "ds_browser_status", "Wait", "checkpoint browser owns feedback")
        app.project_manager.busy = False

        show("export_dialog")
        dpg.configure_item("export_dialog", width=700, height=500)
        app.exports.save()
        check("export_dialog", "export_status", "project changed", "export missing context visible")
        dpg.set_y_scroll("export_dialog_feedback_body", 10000)
        check("export_dialog", "export_status", "project changed", "export feedback survives content scroll")
        dpg.output_frame_buffer(str(args.output / "export-feedback.png"))
        frames()

        show("team")
        app.team.use_user()
        check("team", "team_status", "No account", "team selection explains next step")
        dpg.hide_item("team")
        frames()
        app.save()
        assert "No image" in dpg.get_value("status")
        app.key_press(None, dpg.mvKey_F)
        assert "No image" in dpg.get_value("status")
        checks.append("workspace Save and Fit shortcut explain missing image")
        (args.output / "feedback-smoke.json").write_text(
            json.dumps({"passed": True, "checks": checks}, indent=2), encoding="utf-8"
        )
        print(f"Rendered feedback smoke passed: {len(checks)} checks")
    finally:
        app.pool.shutdown(wait=True)
        app.client.close()
        dpg.destroy_context()


if __name__ == "__main__":
    main()

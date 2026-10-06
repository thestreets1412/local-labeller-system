"""Exercise the rendered desktop against a real loopback server with synthetic data.

This is an automated application smoke check, not a human mouse/DPI acceptance test.
Run with .venv/Scripts/python.exe scripts/desktop_smoke.py --output <directory>.
"""

import argparse
import json
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import patch

import dearpygui.dearpygui as dpg
import uvicorn

from visionlabel.api import create_app
from visionlabel.client import Client, LocalStore
from visionlabel.desktop import Desktop
from visionlabel.domain import uid
from visionlabel.fixtures import bmp_bytes, create_samples
from visionlabel.service import Service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="visionlabel-smoke-") as folder:
        root = Path(folder) / "server"
        password = secrets.token_urlsafe(24)
        service = Service(root)
        service.bootstrap("smoke", password)
        service.close()
        create_samples(root / "inbox", 3)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        if True:
            server = uvicorn.Server(
                uvicorn.Config(
                    create_app(root), host="127.0.0.1", port=port, access_log=False, log_level="error"
                )
            )
            thread = threading.Thread(target=server.run, daemon=True)
            thread.start()
            desktop = None
            client = Client(url)
            try:
                deadline = time.monotonic() + 20
                while True:
                    try:
                        client.login("smoke", password)
                        break
                    except Exception:
                        if not thread.is_alive() or time.monotonic() > deadline:
                            raise RuntimeError("Smoke server did not start.") from None
                        time.sleep(0.1)
                project = client.request(
                    "POST",
                    "/projects",
                    {
                        "name": "Synthetic inspection",
                        "slug": "inspection",
                        "task_type": "detection",
                        "initial_classes": ["Part", "Defect"],
                    },
                    key=uid(),
                )
                client.request(
                    "POST",
                    f"/projects/{project['id']}/imports",
                    {"relative_paths": [p.name for p in sorted((root / "inbox").glob("*.png"))]},
                    key=uid(),
                )
                while len(client.list_all(f"/projects/{project['id']}/images")) < 3:
                    if time.monotonic() > deadline:
                        raise RuntimeError("Import timed out.")
                    time.sleep(0.05)
                desktop = Desktop(url)
                desktop.build()

                def pump_until(predicate, seconds=20):
                    deadline = time.monotonic() + seconds
                    while time.monotonic() < deadline:
                        dpg.run_callbacks(dpg.get_callback_queue())
                        desktop.tick()
                        dpg.render_dearpygui_frame()
                        if predicate():
                            return
                        time.sleep(0.01)
                    raise AssertionError("Desktop timed out: " + desktop.status)

                dpg.set_value("username", "smoke")
                dpg.set_value("password", password)
                desktop.connect()
                pump_until(lambda: bool(desktop.images) and not desktop.busy)
                # Keep private fixture state in the temporary smoke directory.
                desktop.store = LocalStore(url, desktop.client.user["id"], Path(folder) / "client")
                desktop.open_image(desktop.images[0]["id"])
                pump_until(lambda: desktop.image is not None and not desktop.busy)
                assert desktop.claim, desktop.status
                canvas = desktop.canvas
                sx, sy = canvas.transform.screen(70, 70)
                ex, ey = canvas.transform.screen(230, 240)
                canvas.start(sx, sy, desktop.class_id)
                canvas.move(ex, ey)
                canvas.finish()
                desktop.edited()
                desktop.save()
                pump_until(lambda: not desktop.saving)
                assert desktop.head["revision"] == 1, desktop.status
                assert not desktop.editor.dirty
                first_id = desktop.image["id"]
                desktop.navigate(1)
                pump_until(lambda: not desktop.busy and desktop.image["id"] != first_id)
                desktop.open_image(first_id)
                pump_until(lambda: not desktop.busy and desktop.image["id"] == first_id)
                assert len(desktop.editor.content["shapes"]) == 1
                # Test save after undo and redo through real API revisions.
                desktop.editor.selected = desktop.editor.content["shapes"][0]["id"]
                desktop.delete_selected()
                desktop.undo()
                assert len(desktop.editor.content["shapes"]) == 1
                desktop.editor.selected = desktop.editor.content["shapes"][0]["id"]
                desktop.select_class(project["schema"]["entries"][1]["class_id"])
                desktop.save()
                pump_until(lambda: not desktop.saving)
                assert desktop.head["revision"] == 2, desktop.status
                # Recovery never uploads until explicitly restored against the matching base.
                desktop.editor.selected = desktop.editor.content["shapes"][0]["id"]
                desktop.select_class(project["schema"]["entries"][0]["class_id"])
                desktop.keep_then_reload()
                pump_until(lambda: not desktop.busy and dpg.is_item_shown("recovery_dialog"))
                assert desktop.blocked
                desktop.restore_draft()
                desktop.save()
                pump_until(lambda: not desktop.saving)
                assert desktop.head["revision"] == 3, desktop.status
                # A further edit is saved by the real debounce loop, not a direct save call.
                desktop.editor.selected = desktop.editor.content["shapes"][0]["id"]
                desktop.select_class(project["schema"]["entries"][1]["class_id"])
                pump_until(lambda: desktop.head["revision"] == 4 and not desktop.saving)
                assert not desktop.editor.dirty
                desktop.render()
                # Drive the rendered overlay without moving the user's physical mouse.
                saved_content = desktop.editor.content.copy()
                with (
                    patch.object(dpg, "is_item_hovered", return_value=True),
                    patch.object(dpg, "is_key_down", return_value=False),
                    patch.object(desktop, "mouse_position", return_value=canvas.transform.screen(320, 200)),
                ):
                    desktop.set_mode("rectangle")
                    assert desktop.crosshair_visible
                    lines = dpg.get_item_children("crosshair", 2)
                    assert len(lines) == 4
                    horizontal = dpg.get_item_configuration(lines[2])
                    vertical = dpg.get_item_configuration(lines[3])
                    left, top = canvas.transform.screen(0, 0)
                    right, bottom = canvas.transform.screen(canvas.width, canvas.height)
                    assert horizontal["p1"][0] == max(0, left)
                    assert abs(horizontal["p2"][0] - min(dpg.get_item_width("canvas"), right)) < 0.001
                    assert vertical["p1"][1] == max(0, top)
                    assert abs(vertical["p2"][1] - min(dpg.get_item_height("canvas"), bottom)) < 0.001
                    desktop.set_mode("select")
                    assert not desktop.crosshair_visible
                    desktop.set_mode("rectangle")
                    with patch.object(dpg, "is_key_down", return_value=True):
                        desktop.update_crosshair()
                        assert not desktop.crosshair_visible
                    with patch.object(desktop, "mouse_position", return_value=(-1, -1)):
                        desktop.update_crosshair()
                        assert not desktop.crosshair_visible
                    desktop.update_crosshair()
                    assert desktop.crosshair_visible
                    assert desktop.editor.content == saved_content
                    for _ in range(3):
                        dpg.render_dearpygui_frame()
                dpg.output_frame_buffer(str(args.output / "rectangle-workspace.png"))
                for _ in range(8):
                    dpg.render_dearpygui_frame()
                team = desktop.team
                team.open()
                pump_until(lambda: not team.busy)
                assert len(team.users) == 1, dpg.get_value("team_status")
                dpg.set_value("team_username", "junior")
                dpg.set_value("team_display", "Junior inspector")
                dpg.set_value("team_password", "synthetic-junior-password")
                team.create_user()
                pump_until(lambda: not team.busy and len(team.users) == 2)
                label = next(k for k, user in team.users.items() if user["username"] == "junior")
                junior_id = team.users[label]["id"]
                team.pick_member(None, label)
                dpg.set_value("team_role", "annotator")
                team.member(False)
                pump_until(lambda: not team.busy and team.project["project_revision"] == 2)
                members = client.request("GET", f"/projects/{project['id']}/members")["items"]
                assert next(m for m in members if m["id"] == junior_id)["role"] == "annotator"
                team.select_user(None, label)
                dpg.set_value("team_display", "Junior updated")
                team.update_user()
                pump_until(
                    lambda: (
                        not team.busy
                        and any(u["display_name"] == "Junior updated" for u in team.users.values())
                    )
                )
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                dpg.output_frame_buffer(str(args.output / "team-members.png"))
                for _ in range(8):
                    dpg.render_dearpygui_frame()
                team.close()
                # Phase 3: create a segmentation project and use desktop callbacks
                # for polygon completion, editing, save/reload and working QC.
                seg = client.request(
                    "POST",
                    "/projects",
                    {
                        "name": "Synthetic segmentation",
                        "slug": "segmentation",
                        "task_type": "segmentation",
                        "initial_classes": ["Region", "Defect"],
                    },
                    key=uid(),
                )
                desktop.load_project(seg["id"])
                pump_until(lambda: not desktop.busy and desktop.project["id"] == seg["id"])
                desktop.import_inbox()
                pump_until(
                    lambda: (
                        not desktop.busy
                        and not desktop.job
                        and len(desktop.images) == 3
                        and all(i["project_id"] == seg["id"] for i in desktop.images)
                    )
                )
                desktop.open_image(desktop.images[0]["id"])
                pump_until(lambda: not desktop.busy and desktop.image["project_id"] == seg["id"])
                poly = desktop.canvas
                with (
                    patch.object(dpg, "is_item_hovered", return_value=True),
                    patch.object(dpg, "is_key_down", return_value=False),
                ):
                    for point in [(70, 70), (240, 90), (230, 230), (130, 270), (60, 180)]:
                        with patch.object(
                            desktop, "mouse_position", return_value=poly.transform.screen(*point)
                        ):
                            desktop.mouse_down(None, None)
                            desktop.mouse_up(None, None)
                    assert len(poly.draft) == 5 and not desktop.editor.dirty
                    desktop.key_press(None, dpg.mvKey_Return)
                    assert len(desktop.editor.content["shapes"]) == 1 and not poly.draft
                    desktop.set_mode("select")
                    with patch.object(desktop, "mouse_position", return_value=poly.transform.screen(240, 90)):
                        desktop.mouse_down(None, None)
                    with patch.object(
                        desktop, "mouse_position", return_value=poly.transform.screen(270, 100)
                    ):
                        desktop.mouse_move(None, None)
                        desktop.mouse_up(None, None)
                    assert [270, 100] in desktop.editor.content["shapes"][0]["points"]
                desktop.save()
                pump_until(lambda: not desktop.saving and desktop.head["revision"] == 1)
                expected = desktop.editor.content.copy()
                desktop.open_image(desktop.image["id"])
                pump_until(lambda: not desktop.busy)
                assert desktop.editor.content == expected
                desktop.editor.selected = desktop.editor.content["shapes"][0]["id"]
                desktop.render()
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                dpg.output_frame_buffer(str(args.output / "polygon-workspace.png"))
                for _ in range(8):
                    dpg.render_dearpygui_frame()
                desktop.statistics.open()
                pump_until(lambda: not desktop.statistics.busy and desktop.statistics.result is not None)
                assert desktop.statistics.result["total_images"] == 3
                assert sum(c["object_count"] for c in desktop.statistics.result["classes"]) == 1
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                dpg.output_frame_buffer(str(args.output / "working-statistics.png"))
                for _ in range(8):
                    dpg.render_dearpygui_frame()
                dpg.hide_item("statistics")
                # Phase 7: pair BMP/YOLO in the real inbox, preview via desktop,
                # import revision 1, correct a predicted box, save and reload.
                (root / "inbox/spring_img.bmp").write_bytes(bmp_bytes())
                (root / "inbox/spring_img.txt").write_text("0 .2 .2 .2 .2\n", encoding="utf-8")
                pred = client.request(
                    "POST",
                    "/projects",
                    {
                        "name": "Prediction correction",
                        "slug": "predictions",
                        "task_type": "detection",
                        "initial_classes": ["Spring", "Defect"],
                    },
                    key=uid(),
                )
                desktop.load_project(pred["id"])
                pump_until(lambda: not desktop.busy and desktop.project["id"] == pred["id"])
                desktop.show_yolo_import()
                assert "0=Spring" in dpg.get_value("yolo_mapping")
                dpg.set_value("yolo_mapping", "0=Defect\n1=Spring")
                assert desktop.modal_open()
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                dpg.output_frame_buffer(str(args.output / "yolo-import-dialog.png"))
                for _ in range(8):
                    dpg.render_dearpygui_frame()
                desktop.start_yolo_import(True)
                pump_until(lambda: bool(desktop.job))
                pump_until(lambda: desktop.job is None)
                assert client.list_all(f"/projects/{pred['id']}/images") == []
                dpg.hide_item("import_report")
                desktop.show_yolo_import()
                assert dpg.get_value("yolo_mapping") == "0=Defect\n1=Spring"
                desktop.start_yolo_import(False)
                pump_until(lambda: bool(desktop.job))
                pump_until(lambda: desktop.job is None and len(desktop.images) == 4)
                dpg.hide_item("import_report")
                bmp = next(item for item in desktop.images if item["display_filename"] == "spring_img.bmp")
                desktop.open_image(bmp["id"])
                pump_until(
                    lambda: (
                        not desktop.busy and desktop.image is not None and desktop.image["id"] == bmp["id"]
                    )
                )
                assert desktop.head["revision"] == 1 and desktop.editor.content["shapes"][0]["x2"] == 30
                assert (
                    desktop.editor.content["shapes"][0]["class_id"]
                    == pred["schema"]["entries"][1]["class_id"]
                )
                corrected = json.loads(json.dumps(desktop.editor.content))
                corrected["shapes"][0]["x2"] = 40
                desktop.editor.change(corrected)
                desktop.edited()
                desktop.save()
                pump_until(lambda: not desktop.saving and desktop.head["revision"] == 2)
                desktop.open_image(bmp["id"])
                pump_until(lambda: not desktop.busy)
                assert desktop.editor.content["shapes"][0]["x2"] == 40
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                dpg.output_frame_buffer(str(args.output / "bmp-prediction-workspace.png"))
                for _ in range(8):
                    dpg.render_dearpygui_frame()
                # Phase 8: prepare saved detection labels and publish on the desktop's disk.
                # Add a second labeled source so a distinct validation set is possible.
                other = next(item for item in desktop.images if item["id"] != bmp["id"])
                desktop.open_image(other["id"])
                pump_until(lambda: not desktop.busy and desktop.image["id"] == other["id"])
                box = json.loads(json.dumps(corrected))
                desktop.editor.change(box)
                desktop.edited()
                desktop.save()
                pump_until(lambda: not desktop.saving and not desktop.editor.dirty)
                desktop.exports.open()
                dpg.set_value("export_val", 20)
                dpg.set_value("export_test", 0)
                desktop.exports.prepare()
                pump_until(lambda: not desktop.exports.busy)
                assert desktop.exports.prepared, dpg.get_value("export_status")
                assert desktop.exports.prepared["result"]["included"] == 2
                prepared = desktop.exports.prepared
                previous_parent = dpg.get_value("export_parent")
                dpg.set_value("export_name", "exported-dataset")
                desktop.exports.browse_folder()
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                assert not dpg.is_item_shown("export_dialog")
                assert dpg.is_item_shown("export_folder_picker")
                assert dpg.get_item_configuration("export_folder_picker")["modal"]
                desktop.exports.cancel_folder()
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                assert dpg.is_item_shown("export_dialog")
                assert not dpg.is_item_shown("export_folder_picker")
                assert dpg.get_value("export_parent") == previous_parent
                assert desktop.exports.prepared is prepared
                desktop.exports.browse_folder()
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                desktop.exports.choose_folder(None, {"file_path_name": folder})
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                assert dpg.is_item_shown("export_dialog")
                assert not dpg.is_item_shown("export_folder_picker")
                assert dpg.get_value("export_parent") == folder
                assert dpg.get_value("export_name") == "exported-dataset"
                assert dpg.get_value("export_val") == 20
                assert dpg.get_value("export_test") == 0
                assert desktop.exports.prepared is prepared
                desktop.exports.save()
                pump_until(lambda: not desktop.exports.busy)
                exported = Path(folder) / "exported-dataset"
                assert (exported / "data.local.yaml").is_file(), dpg.get_value("export_status")
                manifest = json.loads((exported / "manifest.json").read_text(encoding="utf-8"))
                assert manifest["split"]["actual_counts"] == {"train": 1, "val": 1, "test": 0}
                for _ in range(3):
                    dpg.render_dearpygui_frame()
                dpg.output_frame_buffer(str(args.output / "yolo-export-dialog.png"))
                for _ in range(8):
                    dpg.render_dearpygui_frame()
                result = {
                    "result": "passed",
                    "checks": [
                        "rendered desktop",
                        "real HTTP login/import",
                        "rectangle drag",
                        "save revision 1",
                        "navigate/reload persisted geometry",
                        "delete/undo",
                        "change class/save revision 2",
                        "explicit recovery restore/save revision 3",
                        "2-second autosave/revision 4",
                        "rendered full-image crosshair and select/pan/outside-image suppression",
                        "Team & users: create account, assign annotator role, update account through real HTTP",
                        "Project members: pick account directly from dropdown",
                        "segmentation: click vertices, Enter finish, drag vertex, save/reload exact geometry",
                        "rendered Statistics / QC uses saved polygon annotations",
                        "YOLO mapping dialog, preview and canonical prediction import over HTTP",
                        "BMP render and prediction correction/save/reload revision 2",
                        "YOLO export: real HTTP job, split summary, local download/hash verification and atomic dataset publication",
                        "Export folder picker: exclusive modal, cancel/selection restore Export and preserve prepared dataset/settings",
                    ],
                    "human_mouse_dpi_acceptance": "not performed",
                }
                (args.output / "desktop-smoke.json").write_text(
                    json.dumps(result, indent=2), encoding="utf-8"
                )
                print(json.dumps(result))
            finally:
                if desktop:
                    desktop.request_exit()
                    desktop.release_current()
                    desktop.pool.shutdown(wait=True)
                    desktop.client.close()
                    dpg.destroy_context()
                client.close()
                server.should_exit = True
                thread.join(timeout=15)
                assert not thread.is_alive(), "Smoke server did not stop."


if __name__ == "__main__":
    main()

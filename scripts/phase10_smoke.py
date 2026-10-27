"""Rendered, real-HTTP checkpoint/class/restore journey using synthetic data."""

import argparse
import json
import secrets
import socket
import tempfile
import threading
import time
from pathlib import Path

import dearpygui.dearpygui as dpg
import uvicorn

from visionlabel.api import create_app
from visionlabel.client import Client, LocalStore
from visionlabel.desktop import Desktop
from visionlabel.domain import uid
from visionlabel.fixtures import png_bytes
from visionlabel.service import Service


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="visionlabel-phase10-") as folder:
        root = Path(folder) / "server"
        password = secrets.token_urlsafe(24)
        service = Service(root)
        service.bootstrap("operator", password)
        service.close()
        for i in range(4):
            (root / "inbox" / f"sample-{i}.png").write_bytes(png_bytes(i, 640, 640))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(
            uvicorn.Config(create_app(root), host="127.0.0.1", port=port, log_level="error", access_log=False)
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        client, app = Client(url), None
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    client.login("operator", password)
                    break
                except Exception:
                    if time.monotonic() > deadline:
                        raise
                    time.sleep(0.05)
            project = client.request(
                "POST",
                "/projects",
                {"name": "Phase 10 synthetic", "slug": "phase10", "initial_classes": ["part", "unnecessary"]},
                key=uid(),
            )
            pid = project["id"]
            job = client.request(
                "POST",
                f"/projects/{pid}/imports",
                {"relative_paths": [f"sample-{i}.png" for i in range(4)]},
                key=uid(),
            )
            deadline = time.monotonic() + 30
            while client.request("GET", f"/jobs/{job['job_id']}")["state"] != "succeeded":
                assert time.monotonic() < deadline
                time.sleep(0.05)
            images = client.list_all(f"/projects/{pid}/images")
            for image in images:
                lease = client.request(
                    "POST", f"/images/{image['id']}/claim", {"client_instance_id": client.instance}, key=uid()
                )
                client.request(
                    "PUT",
                    f"/images/{image['id']}/annotation",
                    {
                        "expected_revision": 0,
                        "expected_state_revision": 0,
                        "class_schema_id": project["active_schema_id"],
                        "content": {
                            "image_labels": [],
                            "verified_empty": False,
                            "shapes": [
                                {
                                    "id": uid(),
                                    "type": "rectangle",
                                    "class_id": entry["class_id"],
                                    "x1": 20 + j * 150,
                                    "y1": 50,
                                    "x2": 100 + j * 150,
                                    "y2": 160,
                                    "attributes": {},
                                }
                                for j, entry in enumerate(project["schema"]["entries"])
                            ],
                        },
                    },
                    claim=lease,
                    key=uid(),
                )
                client.request("DELETE", f"/images/{image['id']}/claim", claim=lease)
            app = Desktop(url)
            app.build()

            def pump(predicate, timeout=30):
                deadline = time.monotonic() + timeout
                while time.monotonic() < deadline:
                    dpg.run_callbacks(dpg.get_callback_queue())
                    app.tick()
                    dpg.render_dearpygui_frame()
                    if predicate():
                        return
                    time.sleep(0.005)
                raise AssertionError((app.status, dpg.get_value("ds_status"), dpg.get_value("pm_status")))

            dpg.set_value("username", "operator")
            dpg.set_value("password", password)
            app.connect()
            pump(lambda: len(app.images) == 4 and not app.busy)
            app.store = LocalStore(url, app.client.user["id"], Path(folder) / "client")
            app.open_image(images[0]["id"])
            pump(lambda: not app.busy and app.image is not None)
            manager = app.project_manager

            def open_tools():
                manager.selected = app.project
                manager.datasets.open()
                pump(lambda: not manager.busy and dpg.is_item_shown("dataset_manager"))
                frame = dpg.get_frame_count()
                pump(lambda: dpg.get_frame_count() >= frame + 3)
                return manager.datasets

            panel = open_tools()

            def prepare(kind, label):
                dpg.set_value("ds_label", label)
                dpg.set_value("ds_message", "Synthetic " + label)
                panel.invalidate()
                panel.prepare(kind)
                pump(lambda: not manager.busy)
                assert panel.preview, dpg.get_value("ds_status")
                panel.apply()
                pump(lambda: not manager.busy and not app.busy)
                assert panel.preview is None, dpg.get_value("ds_status")

            prepare("checkpoint", "v1")
            versions = client.request("GET", f"/projects/{pid}/checkpoints")["items"]
            v1 = next(v for v in versions if v["label"] == "v1")
            panel.inspect()
            pump(lambda: not manager.busy)
            pump(lambda: dpg.is_item_shown("checkpoint_browser"))
            panel.view_image()
            pump(lambda: not manager.busy)
            frame = dpg.get_frame_count()
            pump(lambda: dpg.get_frame_count() >= frame + 3)
            assert "rectangle" in dpg.get_value("ds_annotation")
            dpg.output_frame_buffer(str(args.output / "checkpoint-browser.png"))
            pump(lambda: (args.output / "checkpoint-browser.png").exists())
            panel.close_browser()
            pump(lambda: dpg.is_item_shown("dataset_manager"))
            row = panel.class_rows[1]
            dpg.set_value(row[1], False)
            dpg.set_value(row[3], "Remove")
            prepare("schema", "v2-without-unnecessary")
            assert not app.project["schema"]["entries"][1]["active"]
            panel = open_tools()
            label = next(k for k, v in panel.checkpoints.items() if v["id"] == v1["id"])
            dpg.set_value("ds_checkpoints", label)
            panel.compare()
            pump(lambda: not manager.busy)
            assert "changed_annotations" in dpg.get_value("ds_report")
            panel.export()
            pump(lambda: not manager.busy)
            assert app.exports.source_checkpoint["id"] == v1["id"]
            app.exports.prepare()
            pump(lambda: not app.exports.busy)
            assert app.exports.review_confirmation
            app.exports.confirm_review()
            pump(lambda: not app.exports.busy)
            assert app.exports.prepared, dpg.get_value("export_status")
            dpg.hide_item("export_dialog")
            panel = open_tools()
            label = next(k for k, v in panel.checkpoints.items() if v["id"] == v1["id"])
            dpg.set_value("ds_checkpoints", label)
            prepare("restore", "v3-restored-v1")
            assert all(e["active"] for e in app.project["schema"]["entries"])
            for image in client.list_all(f"/projects/{pid}/images"):
                head = client.request("GET", f"/images/{image['id']}/annotation")
                assert len(head["annotation"]["shapes"]) == 2 and head["revision"] == 3
                assert head["status"] == "IN_PROGRESS"
            panel = open_tools()
            dpg.output_frame_buffer(str(args.output / "dataset-checkpoints.png"))
            pump(lambda: (args.output / "dataset-checkpoints.png").exists())
            (args.output / "phase10-smoke.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "journey": [
                            "checkpoint",
                            "historical raster and annotations",
                            "class removal",
                            "diff",
                            "frozen export",
                            "restore",
                        ],
                        "images": 4,
                        "review_after_restore": "IN_PROGRESS",
                        "company_acceptance": False,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            print("Phase 10 rendered HTTP journey passed", flush=True)
        finally:
            if app:
                app.pool.shutdown(wait=True)
                app.client.close()
                dpg.destroy_context()
            client.close()
            server.should_exit = True
            thread.join(20)


if __name__ == "__main__":
    main()

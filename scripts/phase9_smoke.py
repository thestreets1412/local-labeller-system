"""Real HTTP + rendered Phase 9 workflow and 5,000-row scroll check (synthetic only)."""

import argparse
import ctypes
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
    parser.add_argument("--count", type=int, default=5000)
    args = parser.parse_args()
    if args.count < 3:
        parser.error("--count must be at least 3")
    count = args.count
    args.output.mkdir(parents=True, exist_ok=True)
    metrics = {}
    with tempfile.TemporaryDirectory(prefix="visionlabel-phase9-") as folder:
        root = Path(folder) / "server"
        password = secrets.token_urlsafe(24)
        srv = Service(root)
        srv.bootstrap("operator", password)
        srv.close()
        for i in range(count):
            (root / "inbox" / f"image-{i:05}.png").write_bytes(png_bytes(i, 16, 16))
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
            deadline = time.monotonic() + 20
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
                {"name": "Phase 9 synthetic", "slug": "phase9", "initial_classes": ["part", "defect"]},
                key=uid(),
            )
            started = time.monotonic()
            batch_size = min(500, count)
            for offset in range(0, count, batch_size):
                end = min(count, offset + batch_size)
                job = client.request(
                    "POST",
                    f"/projects/{project['id']}/imports",
                    {"relative_paths": [f"image-{i:05}.png" for i in range(offset, end)]},
                    key=uid(),
                )
                deadline = time.monotonic() + 300
                while True:
                    result = client.request("GET", f"/jobs/{job['job_id']}")
                    if result["state"] in ("succeeded", "failed"):
                        assert result["state"] == "succeeded", result
                        assert all(i["outcome"] == "imported" for i in result["result"]["items"])
                        break
                    assert time.monotonic() < deadline, "Import batch timeout"
                    time.sleep(0.1)
                print(f"Imported {end}/{count}", flush=True)
            metrics["import_seconds"] = time.monotonic() - started
            metrics["import_batch_size"] = batch_size
            (args.output / "phase9-import.json").write_text(
                json.dumps({"images": count, "metrics": metrics}, indent=2), encoding="utf-8"
            )
            app = Desktop(url)
            app.build()

            def pump(predicate=lambda: True, seconds=30, frames=4):
                deadline = time.monotonic() + seconds
                frame = 0
                while time.monotonic() < deadline:
                    dpg.run_callbacks(dpg.get_callback_queue())
                    app.tick()
                    dpg.render_dearpygui_frame()
                    frame += 1
                    if predicate() and frame >= frames:
                        return
                    time.sleep(0.005)
                raise AssertionError(app.status)

            dpg.set_value("username", "operator")
            dpg.set_value("password", password)
            started = time.monotonic()
            app.connect()
            pump(lambda: len(app.images) == count and not app.busy)
            metrics["load_render_seconds"] = time.monotonic() - started
            app.store = LocalStore(url, app.client.user["id"], Path(folder) / "client")
            ids = [i["id"] for i in app.images]
            latencies = []
            for index in (0, count // 2 - 1, count - 1, count // 2 - 1, 0):
                started = time.monotonic()
                app.open_image(ids[index])
                pump(
                    lambda index=index: (
                        not app.busy
                        and app.image["id"] == ids[index]
                        and f"[{index + 1}/{count}]" in dpg.get_viewport_configuration(0)["title"]
                    ),
                    frames=8,
                )
                latencies.append(time.monotonic() - started)
                tag = app.image_rows[ids[index]][0]
                assert dpg.is_item_visible(tag), (
                    index,
                    dpg.get_item_state(tag),
                    dpg.get_y_scroll("image_list"),
                )
                assert f"[{index + 1}/{count}]" in dpg.get_viewport_configuration(0)["title"]
            metrics["jump_load_reveal_seconds"] = latencies
            app.editor.change(
                {
                    "verified_empty": False,
                    "image_labels": [],
                    "shapes": [
                        {
                            "id": uid(),
                            "type": "rectangle",
                            "class_id": app.class_id,
                            "x1": 1,
                            "y1": 2,
                            "x2": 12,
                            "y2": 13,
                            "attributes": {},
                        }
                    ],
                }
            )
            app.edited()
            started = time.monotonic()
            app.navigate(1)
            assert not dpg.is_item_shown("dirty_dialog")
            pump(lambda: not app.busy and not app.saving and app.image["id"] == ids[1])
            metrics["save_and_navigate_seconds"] = time.monotonic() - started
            assert client.request("GET", f"/images/{ids[0]}/annotation")["revision"] == 1
            app.open_image(ids[0])
            pump(lambda: not app.busy and app.image["id"] == ids[0])
            app.review.show_settings()
            dpg.set_value("review_self", True)
            dpg.set_value("review_setting_reason", "Synthetic solo workflow acceptance")
            app.review.save_setting()
            pump(lambda: not app.review.busy)
            dpg.set_value("review_advance", False)
            app.review.request("accept")
            pump(lambda: not app.review.busy and not app.busy and app.head["status"] == "REVIEWED_PASS")
            app.editor.selected = app.editor.content["shapes"][0]["id"]
            app.select_class(project["schema"]["entries"][1]["class_id"])
            app.save()
            pump(lambda: not app.saving)
            assert app.head["status"] == "IN_PROGRESS"
            app.review.request("reject")
            dpg.set_value("review_reason", "Wrong class")
            app.review.reject()
            pump(lambda: not app.review.busy and not app.busy and app.head["status"] == "REVIEWED_NG")
            assert app.head["review_comment"] == "Wrong class"
            dpg.set_value("filter", "Needs correction")
            app.refresh_images()
            pump(lambda: len(app.images) == 1)
            assert f"/{count}]" in dpg.get_viewport_configuration(0)["title"]
            app.review.show_history()
            pump(lambda: dpg.is_item_shown("review_history"))
            assert "Reason: Wrong class" in dpg.get_value("review_history_text")
            history = client.request("GET", f"/images/{ids[0]}/reviews")["items"]
            assert len(history) == 2 and history[0]["applicable"] and not history[1]["applicable"]
            dpg.hide_item("review_history")
            pump(frames=4)
            dpg.output_frame_buffer(str(args.output / "phase9-workspace.png"))
            pump(frames=8)

            # A separate reviewer has no editing capability and reviews a queue
            # authored by another user. S advances only after committed PASS.
            reviewer = client.request(
                "POST",
                "/users",
                {"username": "reviewer", "display_name": "Synthetic reviewer", "password": password},
                key=uid(),
            )
            current_project = client.request("GET", f"/projects/{project['id']}")
            client.request(
                "PUT",
                f"/projects/{project['id']}/members/{reviewer['id']}",
                {"role": "reviewer", "expected_project_revision": current_project["project_revision"]},
                key=uid(),
            )
            for iid in ids[1:3]:
                lease = client.request(
                    "POST",
                    f"/images/{iid}/claim",
                    {"mode": "edit", "client_instance_id": client.instance},
                    key=uid(),
                )
                client.request(
                    "PUT",
                    f"/images/{iid}/annotation",
                    {
                        "expected_revision": 0,
                        "expected_state_revision": 0,
                        "class_schema_id": project["active_schema_id"],
                        "content": {"shapes": [], "image_labels": [], "verified_empty": True},
                    },
                    claim=lease,
                    key=uid(),
                )
                client.request("DELETE", f"/images/{iid}/claim", claim=lease)
            dpg.set_value("filter", "Review pending")
            dpg.set_value("username", "reviewer")
            dpg.set_value("password", password)
            app.connect()
            pump(lambda: not app.busy and app.client.user["id"] == reviewer["id"] and len(app.images) == 2)
            app.store = LocalStore(url, reviewer["id"], Path(folder) / "reviewer-client")
            app.review.resume()
            pump(lambda: not app.busy and app.image is not None and app.image["id"] == ids[1])
            assert not app.can_edit() and app.claim["mode"] == "review"
            dpg.set_value("review_advance", True)
            app.key_press(None, dpg.mvKey_S)
            pump(lambda: not app.review.busy and not app.busy and app.image["id"] == ids[2])
            assert client.request("GET", f"/images/{ids[1]}/annotation")["status"] == "REVIEWED_PASS"
            assert app.store.review_cursor(project["id"], "Review pending", "") == ids[2]
            app.review.request("reject")
            dpg.hide_item("review_reject")  # Cancel must not persist a decision.
            pump()
            assert client.request("GET", f"/images/{ids[2]}/annotation")["status"] == "IN_PROGRESS"
            dpg.output_frame_buffer(str(args.output / "phase9-reviewer.png"))
            pump(frames=8)

            class Counters(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("faults", ctypes.c_ulong)] + [
                    (name, ctypes.c_size_t)
                    for name in (
                        "peak",
                        "working",
                        "peak_pool",
                        "pool",
                        "peak_nonpaged",
                        "nonpaged",
                        "pagefile",
                        "peak_pagefile",
                    )
                ]

            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            kernel = ctypes.WinDLL("kernel32")
            kernel.GetCurrentProcess.restype = ctypes.c_void_p
            psapi = ctypes.WinDLL("psapi")
            psapi.GetProcessMemoryInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong]
            if psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
                metrics["peak_working_set_bytes_including_test_server"] = counters.peak
            report = {
                "result": "passed",
                "images": count,
                "metrics": metrics,
                "checks": [
                    f"{count} real imported synthetic images",
                    "jump reveal in both directions",
                    "unfiltered project title under filter",
                    "save-before-navigation without modal",
                    "audited self-review setting",
                    "PASS -> edit -> IN_PROGRESS -> NG and persisted history",
                    "Review-only user, S auto-advance, per-user resume cursor, reject cancellation",
                ],
                "physical_mouse_dpi_acceptance": "not performed",
            }
            (args.output / "phase9-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
            print(json.dumps(report))
        finally:
            if app:
                app.pool.shutdown(wait=True)
                app.client.http.close()
                dpg.destroy_context()
            client.http.close()
            server.should_exit = True
            thread.join(20)


if __name__ == "__main__":
    main()

"""Rendered storage UI smoke against a synthetic HTTP service; no client cache."""

import json
import socket
import tempfile
import threading
import time
from pathlib import Path

import dearpygui.dearpygui as dpg
import uvicorn

from visionlabel.api import create_app
from visionlabel.client import Client
from visionlabel.desktop import Desktop
from visionlabel.service import Service


def main():
    output = Path("docs/verification-artifacts/phase11")
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="visionlabel-storage-ui-") as folder:
        root = Path(folder) / "server"
        service = Service(root)
        service.bootstrap("operator", "synthetic-storage-password")
        service.close()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}"
        server = uvicorn.Server(
            uvicorn.Config(create_app(root), host="127.0.0.1", port=port, log_level="error", access_log=False)
        )
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        app = None
        client = Client(url)
        try:
            deadline = time.monotonic() + 30
            while True:
                try:
                    client.login("operator", "synthetic-storage-password")
                    break
                except Exception:
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
            app = Desktop(url)
            app.build()
            # Do not call connect(): that separate workflow creates the normal client cache.
            app.client = client
            panel = app.project_manager.storage
            dpg.hide_item("connection")
            dpg.configure_item("storage_manager", width=700, height=570, pos=(10, 10))

            def pump(predicate):
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    dpg.run_callbacks(dpg.get_callback_queue())
                    app.tick()
                    dpg.render_dearpygui_frame()
                    if predicate():
                        return
                    time.sleep(0.005)
                raise AssertionError(dpg.get_value("storage_status"))

            panel.show()
            pump(lambda: not panel.busy)
            pump(lambda: dpg.is_item_visible("storage_manager"))
            assert str(root) in dpg.get_value("storage_scope")
            panel.preview_cleanup()
            assert "No archives selected" in dpg.get_value("storage_status")
            panel.make_report()
            pump(lambda: not panel.busy)
            assert panel.report_id
            panel.open_report()
            pump(lambda: not panel.busy)
            assert "reclaimable_asset_bytes" in dpg.get_value("storage_result")
            panel.preview_policy()
            pump(lambda: not panel.busy)
            assert panel.policy_preview
            panel.apply_policy()
            pump(lambda: not panel.busy)
            assert panel.policy["generation"] == 2
            panel.refresh()
            pump(lambda: not panel.busy)
            frame = dpg.get_frame_count()
            pump(lambda: dpg.get_frame_count() > frame + 3)
            screenshot = output / "storage-usage.png"
            dpg.output_frame_buffer(str(screenshot.absolute()))
            pump(screenshot.exists)
            (output / "storage-smoke.json").write_text(
                json.dumps(
                    {
                        "passed": True,
                        "window_size": [700, 570],
                        "checks": [
                            "exact root",
                            "current-window missing-selection feedback",
                            "root report create/read",
                            "policy preview/apply",
                            "HTTP background completion",
                        ],
                        "company_acceptance": False,
                    },
                    indent=2,
                )
                + "\n"
            )
            print("Storage UI HTTP smoke passed", flush=True)
        finally:
            if app:
                app.pool.shutdown(wait=True)
                dpg.destroy_context()
            client.close()
            server.should_exit = True
            thread.join(30)


if __name__ == "__main__":
    main()

"""Synthetic rendered Accept timing; no user datasets or canonical shortcuts."""

import argparse
import json
import platform
import secrets
import socket
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

import dearpygui.dearpygui as dpg
import uvicorn

from visionlabel.api import create_app
from visionlabel.client import Client, LocalStore
from visionlabel.desktop import Desktop
from visionlabel.domain import uid
from visionlabel.fixtures import png_bytes
from visionlabel.service import Service
from visionlabel.texture import _native_convert


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--legacy-reload", action="store_true")
    parser.add_argument("--fallback", action="store_true")
    parser.add_argument("--edge", type=int, default=640)
    parser.add_argument("--dirty", action="store_true")
    args = parser.parse_args()
    if args.fallback:
        import visionlabel.texture as texture_module

        texture_module._native_convert = None
    stages = defaultdict(list)
    measuring = False
    with tempfile.TemporaryDirectory(prefix="visionlabel-review-") as folder:
        root = Path(folder) / "server"
        password = secrets.token_urlsafe(24)
        service = Service(root)
        service.bootstrap("operator", password)
        service.close()
        for i in range(args.count):
            (root / "inbox" / f"{i}.png").write_bytes(png_bytes(i, args.edge, args.edge))
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
                {"name": "Review benchmark", "slug": "review", "initial_classes": ["part"]},
                key=uid(),
            )
            pid = project["id"]
            client.request(
                "PUT",
                f"/projects/{pid}/review-settings",
                {
                    "expected_project_revision": project["project_revision"],
                    "allow_self_review": True,
                    "reason": "Synthetic benchmark",
                },
                key=uid(),
            )
            for offset in range(0, args.count, 500):
                job = client.request(
                    "POST",
                    f"/projects/{pid}/imports",
                    {"relative_paths": [f"{i}.png" for i in range(offset, min(args.count, offset + 500))]},
                    key=uid(),
                )
                deadline = time.monotonic() + 300
                while True:
                    result = client.request("GET", f"/jobs/{job['job_id']}")
                    if result["state"] in ("succeeded", "failed"):
                        assert result["state"] == "succeeded", result
                        break
                    assert time.monotonic() < deadline
                    time.sleep(0.05)
            app = Desktop(url)
            app.build()
            if args.legacy_reload:
                normal_open = app.open_image

                def legacy_open(*a, **kw):
                    if kw.get("reuse_raster"):
                        app.review.refresh()
                        app.populate_images()
                        kw["reuse_raster"] = False
                    return normal_open(*a, **kw)

                app.open_image = legacy_open

            def pump(predicate):
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    dpg.run_callbacks(dpg.get_callback_queue())
                    app.tick()
                    dpg.render_dearpygui_frame()
                    if predicate():
                        return
                    time.sleep(0.001)
                raise AssertionError(app.status)

            dpg.set_value("username", "operator")
            dpg.set_value("password", password)
            app.connect()
            pump(lambda: len(app.images) == args.count and not app.busy)
            app.store = LocalStore(url, app.client.user["id"], Path(folder) / "client")
            original = app.client.request

            def timed(method, path, *a, **kw):
                start = time.perf_counter()
                try:
                    return original(method, path, *a, **kw)
                finally:
                    if measuring:
                        operation = path.rsplit("/", 1)[-1]
                        if len(operation) == 36:
                            operation = "image"
                        stages[method + " " + operation].append(time.perf_counter() - start)

            app.client.request = timed
            app.open_image(app.images[0]["id"])
            pump(lambda: not app.busy and app.image is not None)
            for obj, attribute, stage in (
                (app.store, "decode_image", "decode"),
                (app, "populate_images", "list-update"),
            ):
                original_stage = getattr(obj, attribute)

                def stage_wrapper(*a, _original=original_stage, _stage=stage, **kw):
                    start = time.perf_counter()
                    try:
                        return _original(*a, **kw)
                    finally:
                        if measuring:
                            stages[_stage].append(time.perf_counter() - start)

                setattr(obj, attribute, stage_wrapper)
            dpg.set_value("review_advance", False)
            samples = []
            for trial in range(args.samples + 1):
                content = {
                    "verified_empty": False,
                    "image_labels": [],
                    "shapes": [
                        {
                            "id": uid(),
                            "type": "rectangle",
                            "class_id": app.class_id,
                            "x1": 10 + j * 30,
                            "y1": 20,
                            "x2": 30 + j * 30,
                            "y2": 100,
                            "attributes": {},
                        }
                        for j in range(7)
                    ],
                }
                app.editor.change(content)
                app.edited()
                app.save()
                pump(lambda: not app.saving)
                assert app.head["status"] == "IN_PROGRESS", app.status
                measuring = trial > 0
                if args.dirty:
                    content["shapes"][0]["x1"] += 1
                    app.editor.change(content)
                    app.edited()
                start = time.perf_counter()
                app.review.request("accept")
                pump(lambda: not app.review.busy and not app.busy and app.head["status"] == "REVIEWED_PASS")
                elapsed = time.perf_counter() - start
                measuring = False
                if trial:
                    samples.append(elapsed)

            def summary(values):
                ordered = sorted(values)
                return {
                    "count": len(values),
                    "p50_ms": ordered[len(ordered) // 2] * 1000,
                    "p95_ms": ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000,
                }

            result = {
                "scenario": f"maintainer, {'dirty' if args.dirty else 'clean'}, same image, seven boxes, {args.edge}x{args.edge}, warm",
                "legacy_reload_simulation": args.legacy_reload,
                "project_images": args.count,
                "python": platform.python_version(),
                "platform": platform.platform(),
                "native_texture": _native_convert is not None and not args.fallback,
                "interaction": summary(samples),
                "http_stages": {k: summary(v) for k, v in stages.items()},
                "samples_seconds": samples,
                "limitations": "Local synthetic data; excludes company LAN/HDD, cold loads and auto-advance; dirty state is identified in scenario.",
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(
                json.dumps({k: v for k, v in result.items() if k != "samples_seconds"}, indent=2), flush=True
            )
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

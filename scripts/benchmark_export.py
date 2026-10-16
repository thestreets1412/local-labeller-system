"""Measure prepare and client save with unique synthetic BMPs and seven YOLO boxes.

Fixture setup is excluded. HTTP transport is in-process, so this is not a LAN benchmark.
"""

import argparse
import json
import tempfile
import time
from pathlib import Path

import httpx

from visionlabel.client import Client
from visionlabel.database import row
from visionlabel.domain import Problem, uid
from visionlabel.fixtures import bmp_bytes
from visionlabel.service import Service
from visionlabel.working_export import export_archive, start_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--mode", choices=("yolo",), default="yolo")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.count <= 50000:
        parser.error("Count must be between 1 and 50000.")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="import-benchmark-", dir=args.output.parent) as directory:
        srv = Service(Path(directory))
        try:
            srv.bootstrap("benchmark", "synthetic-benchmark-password")
            user = srv.authenticate(srv.login("benchmark", "synthetic-benchmark-password")["token"])
            proj = srv.create_project(
                user,
                {
                    "name": "Synthetic benchmark",
                    "slug": "benchmark",
                    "task_type": "detection",
                    "initial_classes": ["part"],
                },
                uid(),
                uid(),
            )
            paths = []
            raw = bytearray(bmp_bytes(640, 640))
            for index in range(args.count):
                raw[54:57] = index.to_bytes(3, "little")
                name = f"sample-{index:05d}"
                (srv.inbox / f"{name}.bmp").write_bytes(raw)
                paths.append(f"{name}.bmp")
                if args.mode == "yolo":
                    (srv.inbox / f"{name}.txt").write_text("0 0.5 0.5 0.25 0.25\n" * 7)
            body = {"relative_paths": paths, "dry_run": False}
            if args.mode == "yolo":
                body["yolo"] = {
                    "class_schema_id": proj["active_schema_id"],
                    "class_mapping": {"0": proj["schema"]["entries"][0]["class_id"]},
                    "empty_is_verified": False,
                }
            started = time.perf_counter()
            jid = srv.import_images(user, proj["id"], body, uid(), uid())["job_id"]
            # Same executor: this barrier runs after the import completes, without report polling overhead.
            srv.pool.submit(lambda: None).result(timeout=3600)
            with srv.db.engine.connect() as conn:
                job = row(conn, "SELECT * FROM jobs WHERE id=?", (jid,))
            assert job["state"] == "succeeded", job["error_json"]
            result = json.loads(job["result_json"])
            assert len(result["items"]) == args.count
            assert all(i["outcome"] == "imported" for i in result["items"])
            if args.mode == "yolo":
                assert all(i["revision"] == 1 for i in result["items"])
            started = time.perf_counter()
            options = {"validation_percent": 20, "test_percent": 10, "seed": 42}
            try:
                start_export(srv, user, proj["id"], options, uid(), uid())
                raise AssertionError("Expected review confirmation")
            except Problem as exc:
                assert exc.code == "REVIEW_CONFIRMATION_REQUIRED"
                options["confirmation"] = exc.details["confirmation"]
            job_id = start_export(srv, user, proj["id"], options, uid(), uid())["job_id"]
            srv.pool.submit(lambda: None).result(timeout=3600)
            prepare_seconds = time.perf_counter() - started
            with srv.db.engine.connect() as conn:
                job = row(conn, "SELECT * FROM jobs WHERE id=?", (job_id,))
            assert job["state"] == "succeeded", job["error_json"]
            result = json.loads(job["result_json"])

            class ArchiveStream(httpx.SyncByteStream):
                def __iter__(self):
                    with (srv.root / "export-cache" / f"{job_id}.zip").open("rb") as source:
                        while chunk := source.read(1024 * 1024):
                            yield chunk

            def respond(request):
                export_archive(srv, user, job_id)
                return httpx.Response(200, stream=ArchiveStream())

            client = Client()
            client.http.close()
            client.http = httpx.Client(
                base_url="http://127.0.0.1/api/v1", transport=httpx.MockTransport(respond)
            )
            started = time.perf_counter()
            try:
                client.download_export(job_id, Path(directory) / "dataset", result)
            finally:
                client.close()
            save_seconds = time.perf_counter() - started
            report = {
                "images": args.count,
                "dimensions": [640, 640],
                "bytes_each": len(raw),
                "archive_bytes": result["bytes"],
                "prepare_seconds": prepare_seconds,
                "save_seconds": save_seconds,
                "performance": result.get("performance"),
                "scope": "One local synthetic run; excludes fixture setup. In-process HTTP transport, real service/files/hash/fsync. Not the company HDD/LAN dataset.",
            }
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report), flush=True)
        finally:
            srv.close()


if __name__ == "__main__":
    main()

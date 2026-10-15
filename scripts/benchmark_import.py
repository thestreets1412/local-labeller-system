"""Benchmark the real service import path using unique synthetic BMPs and optional YOLO labels."""

import argparse
import json
import tempfile
import time
from pathlib import Path

from visionlabel.database import row
from visionlabel.domain import uid
from visionlabel.fixtures import bmp_bytes
from visionlabel.service import Service


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--mode", choices=("inbox", "yolo"), required=True)
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
            elapsed = time.perf_counter() - started
            with srv.db.engine.connect() as conn:
                job = row(conn, "SELECT * FROM jobs WHERE id=?", (jid,))
            assert job["state"] == "succeeded", job["error_json"]
            result = json.loads(job["result_json"])
            assert len(result["items"]) == args.count
            assert all(i["outcome"] == "imported" for i in result["items"])
            if args.mode == "yolo":
                assert all(i["revision"] == 1 for i in result["items"])
            report = {
                "mode": args.mode,
                "images": args.count,
                "dimensions": [640, 640],
                "bytes_each": len(raw),
                "seconds": elapsed,
                "performance": result.get("performance"),
                "scope": "Local synthetic service run; excludes fixture creation, UI and HTTP polling. Not the production HDD dataset.",
            }
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report), flush=True)
        finally:
            srv.close()


if __name__ == "__main__":
    main()

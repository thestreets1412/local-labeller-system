"""Synthetic Phase 11 scale acceptance. Never accepts a production root."""

import argparse
import json
import shutil
import tempfile
import time
from pathlib import Path

from visionlabel.database import row
from visionlabel.domain import Problem, uid
from visionlabel.fixtures import bmp_bytes
from visionlabel.service import Service
from visionlabel.storage_inventory import scan_storage
from visionlabel.working_export import start_export


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--images", type=int, default=5400)
    parser.add_argument(
        "--output", type=Path, default=Path("docs/verification-artifacts/phase11/storage-results.json")
    )
    args = parser.parse_args()
    assert 1 <= args.images <= 10000
    with tempfile.TemporaryDirectory(prefix="visionlabel-phase11-synthetic-") as directory:
        root = Path(directory)
        raw = bytearray(bmp_bytes(304, 304))
        expected = len(raw) * args.images
        free = shutil.disk_usage(root).free
        print(
            json.dumps(
                {
                    "synthetic_root": str(root),
                    "source_bytes": expected,
                    "free_bytes": free,
                    "estimated_peak_bytes": expected * 6 + 1024**3,
                }
            ),
            flush=True,
        )
        assert free > expected * 6 + 1024**3
        srv = Service(root)
        try:
            srv.bootstrap("benchmark", "synthetic-benchmark-password")
            user = srv.authenticate(srv.login("benchmark", "synthetic-benchmark-password")["token"])
            project = srv.create_project(
                user,
                {
                    "name": "Storage scale",
                    "slug": "storage-scale",
                    "task_type": "detection",
                    "initial_classes": ["part"],
                },
                uid(),
                uid(),
            )
            paths = []
            for index in range(args.images):
                raw[54:57] = index.to_bytes(3, "little")
                name = f"sample-{index:05d}"
                (srv.inbox / f"{name}.bmp").write_bytes(raw)
                (srv.inbox / f"{name}.txt").write_text("0 0.5 0.5 0.25 0.25\n")
                paths.append(f"{name}.bmp")
            job_id = srv.import_images(
                user,
                project["id"],
                {
                    "relative_paths": paths,
                    "dry_run": False,
                    "yolo": {
                        "class_schema_id": project["active_schema_id"],
                        "class_mapping": {"0": project["schema"]["entries"][0]["class_id"]},
                        "empty_is_verified": False,
                    },
                },
                uid(),
                uid(),
            )["job_id"]

            def job(ident):
                srv.pool.submit(lambda: None).result(timeout=7200)
                with srv.db.engine.connect() as conn:
                    result = row(conn, "SELECT * FROM jobs WHERE id=?", (ident,))
                assert result["state"] == "succeeded", result["error_json"]
                return json.loads(result["result_json"])

            imported = job(job_id)
            assert len(imported["items"]) == args.images
            assert all(item["outcome"] == "imported" for item in imported["items"])
            # Remove only explicitly generated inputs in this owned synthetic fixture.
            for name in paths:
                (srv.inbox / name).unlink()
                (srv.inbox / name).with_suffix(".txt").unlink()
            cache = srv.export_cache

            def policy(budget, automatic):
                body = {
                    "expected_generation": cache.policy()["generation"],
                    "max_bytes": budget,
                    "max_age_days": 7,
                    "automatic_enabled": automatic,
                }
                preview = cache.preview_policy(user, body)
                return cache.update_policy(user, body | {"preview_token": preview["token"]})

            policy(16 * 1024**3, False)
            exports = []
            for seed in (42, 43, 44, 44):
                started = time.perf_counter()
                options = {"validation_percent": 20, "test_percent": 10, "seed": seed}
                try:
                    start_export(srv, user, project["id"], options, uid(), uid())
                    raise AssertionError("Expected review confirmation")
                except Problem as exc:
                    assert exc.code == "REVIEW_CONFIRMATION_REQUIRED"
                    options["confirmation"] = exc.details["confirmation"]
                ident = start_export(srv, user, project["id"], options, uid(), uid())["job_id"]
                result = job(ident)
                exports.append(
                    {
                        "seconds": time.perf_counter() - started,
                        "bytes": result["bytes"],
                        "reused": result.get("reused", False),
                    }
                )
                print(json.dumps(exports[-1]), flush=True)
            assert exports[-1]["reused"]
            assert len(list((root / "export-cache").glob("*.zip"))) == 3
            started = time.perf_counter()
            before = scan_storage(root, deep=True, boundary=cache.boundary)
            scan_seconds = time.perf_counter() - started
            before_bytes = sum(a["bytes"] for a in cache.artifacts() if a["state"] == "ACTIVE")
            # At small smoke scale, use two archives as the budget; scale run uses 4 GiB.
            budget = min(4 * 1024**3, exports[0]["bytes"] * 2 + 1024)
            policy(budget, True)
            cache.maintain()
            after_bytes = sum(a["bytes"] for a in cache.artifacts() if a["state"] == "ACTIVE")
            assert after_bytes <= budget < before_bytes
            assert len(list((root / "managed/assets").rglob("*.bmp"))) == args.images
            after = scan_storage(root, deep=True, boundary=cache.boundary)
            report = {
                "images": args.images,
                "source_bytes": expected,
                "dimensions": [304, 304],
                "exports": exports,
                "scan_seconds": scan_seconds,
                "cache_before_bytes": before_bytes,
                "cache_after_bytes": after_bytes,
                "reclaimed_bytes": before_bytes - after_bytes,
                "budget_bytes": budget,
                "before_categories": before["categories"],
                "after_categories": after["categories"],
                "warnings": after["warnings"],
                "scope": "Synthetic local disk only. File-size totals, not allocated clusters or measured transient peak; no company data or LAN acceptance.",
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report), flush=True)
        finally:
            srv.close()


if __name__ == "__main__":
    main()

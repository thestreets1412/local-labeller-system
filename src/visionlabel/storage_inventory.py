"""Root-contained storage accounting. Asset classification never authorizes deletion."""

import json
import sqlite3
import time
from collections import defaultdict

from .domain import uid
from .storage_boundary import StorageBoundary


def scan_storage(root, *, deep=False, boundary=None):
    boundary = boundary or StorageBoundary(root)
    report = {
        "schema_version": 1,
        "root": str(boundary.root),
        "root_identity": boundary.identity,
        "scan_id": uid(),
        "deep": deep,
        "complete": True,
        "warnings": [],
        "categories": [],
        "assets": [],
        "project_logical_bytes": {},
        "totals": {},
    }
    categories: dict[str, dict[str, int]] = defaultdict(lambda: {"count": 0, "bytes": 0})
    files = {}
    for entry in boundary.walk():
        if entry["blocked"]:
            report["warnings"].append(f"Blocked entry: {entry['path']}")
            continue
        if entry["directory"]:
            continue
        path = entry["path"]
        category = next(
            (
                prefix
                for prefix in (
                    "managed/assets",
                    "managed/projects",
                    "managed/export-receipts",
                    "export-cache",
                    "inbox",
                    "db",
                    "reports",
                )
                if path.startswith(prefix + "/")
            ),
            "other",
        )
        categories[category]["count"] += 1
        categories[category]["bytes"] += entry["bytes"]
        files[path] = entry
    registered = {}
    references = set()
    memberships = defaultdict(list)
    logical: dict[str, int] = defaultdict(int)
    try:
        with boundary.database() as folder:
            # Lock DB path against replacement while SQLite opens it; memory temp avoids external spill.
            with boundary.entry("db/data_tracking.sqlite3") as handle:
                from .storage_boundary import info

                if info(handle)["blocked"]:
                    raise ValueError("Database is a reparse point")
                conn = sqlite3.connect((folder / "data_tracking.sqlite3").as_uri() + "?mode=ro", uri=True)
                try:
                    conn.execute("PRAGMA temp_store=MEMORY")
                    conn.execute("BEGIN")
                    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                    version = conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                    if version not in ("0008", "0009"):
                        raise ValueError("Unsupported database schema")
                    conn.row_factory = sqlite3.Row
                    registered = {
                        "managed/" + r["blob_path"]: dict(r) for r in conn.execute("SELECT * FROM assets")
                    }
                    for r in conn.execute(
                        "SELECT i.asset_sha256,i.project_id,i.archived,p.archived AS project_archived FROM images i JOIN projects p ON p.id=i.project_id"
                    ):
                        memberships[r["asset_sha256"]].append(dict(r))

                    def inspect(value):
                        if isinstance(value, dict):
                            for key, child in value.items():
                                if key in ("blob_path", "asset_path", "annotation_path") and isinstance(
                                    child, str
                                ):
                                    relative = "managed/" + child
                                    references.add(relative)
                                    boundary.parts(relative)
                                    entry = files.get(relative)
                                    if not entry:
                                        raise ValueError("Missing or blocked historical reference")
                                else:
                                    inspect(child)
                        elif isinstance(value, list):
                            for child in value:
                                inspect(child)

                    for table in (
                        "class_schemas",
                        "annotation_revisions",
                        "dataset_checkpoints",
                        "dataset_operations",
                        "export_receipts",
                    ):
                        if table not in tables:
                            continue
                        for r in conn.execute(f"SELECT blob_path,sha256 FROM {table}"):
                            relative = "managed/" + r[0]
                            references.add(relative)
                            with boundary.open_read(relative) as stream:
                                raw = stream.read()
                            from .domain import digest

                            if digest(raw) != r[1]:
                                raise ValueError("Historical metadata checksum mismatch")
                            inspect(json.loads(raw))
                    for table, column in (("jobs", "payload_json"), ("export_candidates", "snapshot_json")):
                        if table in tables:
                            for r in conn.execute(f"SELECT {column} FROM {table}"):
                                inspect(json.loads(r[0]))
                finally:
                    conn.close()
    except Exception as exc:
        # Diagnostic failure is explicit; never convert failed reference traversal to 'unreferenced'.
        report["warnings"].append(f"Reference scan incomplete: {type(exc).__name__}: {exc}")
    report["complete"] = not report["warnings"]
    for path in sorted(set(registered) | {p for p in files if p.startswith("managed/assets/")}):
        entry = files.get(path)
        record = registered.get(path)
        sha = record["sha256"] if record else path.rsplit("/", 1)[-1].split(".")[0]
        refs = memberships[sha]
        active = [r for r in refs if not r["archived"] and not r["project_archived"]]
        category = (
            "active/shared"
            if active
            else "history-only"
            if refs or path in references
            else "registered/unexplained"
            if record
            else "unknown"
        )
        reasons = (
            ["Registered assets are retained."]
            if record
            else ["Report only; asset deletion is not available in Phase 11."]
        )
        valid = bool(entry)
        if entry and record and entry["bytes"] != record["byte_size"]:
            valid = False
        if entry and deep:
            try:
                valid = valid and boundary.hash(path) == sha
            except Exception as exc:
                valid = False
                report["warnings"].append(f"Cannot hash {path}: {exc}")
        if not valid:
            category = "corrupt/missing/unknown"
            report["complete"] = False
        elif (
            not record
            and path not in references
            and deep
            and report["complete"]
            and entry["mtime"] <= time.time() - 7 * 86400
        ):
            category = "file-only orphan candidate"
        size = entry["bytes"] if entry else 0
        projects = sorted({r["project_id"] for r in refs})
        for pid in projects:
            logical[pid] += size
        report["assets"].append(
            {
                "hash": sha,
                "path": path,
                "bytes": size,
                "category": category,
                "project_ids": projects,
                "reasons": reasons,
            }
        )
    if not report["complete"]:
        for asset in report["assets"]:
            if asset["category"] == "file-only orphan candidate":
                asset["category"] = "unknown"
    report["project_logical_bytes"] = dict(logical)
    report["categories"] = [{"name": k, **v} for k, v in sorted(categories.items())]
    report["totals"] = {
        "bytes": sum(v["bytes"] for v in categories.values()),
        "asset_bytes": sum(a["bytes"] for a in report["assets"]),
        "reclaimable_asset_bytes": 0,
        "allocated_bytes": None,
    }
    return report

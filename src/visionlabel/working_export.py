"""Frozen working-data exports. These are not approved dataset releases."""

import hashlib
import json
import os
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

from pydantic import Field, model_validator

from .contracts import StrictModel
from .database import row, rows
from .domain import Problem, canonical, digest, uid, validate_content
from .formats import FORMAT_VERSION, classification_mapping, yolo_config, yolo_labels
from .imaging import exif_orientation
from .splitting import PARTITIONS, effective_groups, targets
from .storage import contained

PROFILE = "working-yolo-export-1"


class ExportRequest(StrictModel):
    validation_percent: int = Field(default=20, ge=1, le=99, strict=True)
    test_percent: int = Field(default=10, ge=0, le=98, strict=True)
    seed: int = Field(default=42, ge=0, le=2**31 - 1, strict=True)

    @model_validator(mode="after")
    def train_nonempty(self):
        if self.validation_percent + self.test_percent >= 100:
            raise ValueError("Validation plus test must be below 100 percent.")
        return self


def split_items(items, options):
    """Seeded group allocation; training class coverage takes precedence over ratios."""
    ratios = {"val": options["validation_percent"] * 100, "test": options["test_percent"] * 100}
    ratios["train"] = 10000 - ratios["val"] - ratios["test"]
    active = [p for p in PARTITIONS if ratios[p]]
    groups = effective_groups(items, True)
    if len(groups) < len(active):
        raise Problem("TOO_FEW_GROUPS", "Add labeled images/groups or reduce test to 0 percent.")
    ordered = sorted(
        groups, key=lambda g: (digest(f"{PROFILE}|{options['seed']}|{g['id']}".encode()), g["id"])
    )
    rank = {g["id"]: i for i, g in enumerate(ordered)}
    desired = targets(len(items), ratios)
    counts = dict.fromkeys(PARTITIONS, 0)
    presence: dict[str, Counter] = {p: Counter() for p in PARTITIONS}
    allocated: dict[str, str] = {}

    def place(group, part):
        old = allocated.get(group["id"])
        if old:
            counts[old] -= group["size"]
            presence[old].subtract(group["classes"])
        allocated[group["id"]] = part
        counts[part] += group["size"]
        presence[part].update(group["classes"])

    # Cover rare classes first; seeded order breaks equal choices reproducibly.
    totals = Counter(c for g in groups for c in g["classes"])
    for cls in sorted(totals, key=lambda c: (totals[c], c)):
        if cls == "__empty__":
            continue
        if not presence["train"][cls]:
            candidate = min(
                (g for g in ordered if g["classes"][cls]),
                key=lambda g: (g["size"], rank[g["id"]]),
            )
            place(candidate, "train")
    for group in ordered:
        if group["id"] not in allocated:
            part = min(
                active,
                key=lambda p: (
                    (counts[p] + group["size"] - desired[p]) ** 2 - (counts[p] - desired[p]) ** 2,
                    PARTITIONS.index(p),
                ),
            )
            place(group, part)
    # A requested partition must never silently disappear after rounding.
    for part in active:
        if counts[part]:
            continue
        candidates = []
        for group in ordered:
            old = allocated[group["id"]]
            if counts[old] <= group["size"]:
                continue
            if old == "train" and any(
                presence[old][c] <= n for c, n in group["classes"].items() if c != "__empty__"
            ):
                continue
            candidates.append(group)
        if not candidates:
            raise Problem(
                "TRAIN_COVERAGE",
                "Cannot keep all classes in train and populate validation/test. Add labeled examples/groups or reduce test to 0 percent.",
            )
        place(min(candidates, key=lambda g: (g["size"], rank[g["id"]])), part)
    assignments = {i["image_id"]: allocated[g["id"]] for g in groups for i in g["items"]}
    return assignments, {
        "algorithm": PROFILE,
        "seed": options["seed"],
        "requested_percent": {p: ratios[p] / 100 for p in PARTITIONS},
        "actual_counts": counts,
        "actual_percent": {p: counts[p] * 100 / len(items) for p in PARTITIONS},
        "class_image_counts": {c: {p: presence[p][c] for p in PARTITIONS} for c in sorted(totals)},
        "group_count": len(groups),
        "note": "Ratios are targets; rounding, groups and training class coverage can change actual percentages.",
    }


def start_export(srv, user, project_id, body, key, request_id):
    from .service import now

    body = ExportRequest.model_validate(body).model_dump()
    with srv.db.transaction() as conn:
        project = srv.maintain(conn, user, project_id)
        replay = srv.replay(conn, user, f"working-export/{project_id}", key, body)
        if replay:
            return replay
        schema = row(conn, "SELECT * FROM class_schemas WHERE id=?", (project["active_schema_id"],))
        records = rows(
            conn,
            "SELECT i.id AS image_id,i.asset_sha256,i.display_filename,i.group_key,a.width,a.height,a.extension,a.blob_path AS asset_path,h.status,h.current_revision,r.schema_id,r.blob_path AS annotation_path,r.sha256 AS annotation_sha256 FROM images i JOIN assets a ON a.sha256=i.asset_sha256 JOIN annotation_heads h ON h.image_id=i.id LEFT JOIN annotation_revisions r ON r.image_id=i.id AND r.revision=h.current_revision WHERE i.project_id=? AND i.archived=0 ORDER BY i.id",
            (project_id,),
        )
        snapshot = {
            "project_id": project_id,
            "task_type": project["task_type"],
            "schema": schema,
            "records": records,
            "options": body,
        }
        job_id = uid()
        conn.exec_driver_sql(
            "INSERT INTO jobs (id,project_id,created_by,type,state,payload_json,progress_total,created_at,updated_at) VALUES (?,?,?,'working-export','queued',?,?,?,?)",
            (job_id, project_id, user["id"], canonical(snapshot).decode(), len(records), now(), now()),
        )
        result = {"job_id": job_id}
        srv.remember(conn, user, f"working-export/{project_id}", key, body, result, 202)
        srv.audit(
            conn,
            user,
            "working_export.requested",
            job_id,
            project_id,
            {"snapshot_sha256": digest(canonical(snapshot)), "options": body},
            request_id,
        )
    srv.pool.submit(run_export, srv, user, job_id, snapshot, request_id)
    return result


PREPARE_SCRIPT = '''"""Regenerate local training paths after moving this dataset. Standard library only."""
import json
from pathlib import Path
root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
if manifest["task_type"] == "classification":
    print("Classification dataset:", root)
else:
    template = (root / "data.yaml").read_text(encoding="utf-8")
    local = "path: " + json.dumps(root.as_posix(), ensure_ascii=False) + "\\n" + template.split("\\n", 1)[1]
    (root / "data.local.yaml").write_text(local, encoding="utf-8")
    print("Training YAML:", root / "data.local.yaml")
'''


def prepare_snapshot(srv, snapshot):
    schema = snapshot["schema"]
    document = srv.blobs.json(schema["blob_path"], schema["sha256"])
    classes = [
        {
            "class_id": e["class_id"],
            "export_index": e["export_index"],
            "name": e["display_name"],
            "key": e["stable_key"],
            "active": e["active"],
        }
        for e in document["entries"]
    ]
    included, excluded = [], []
    for record in snapshot["records"]:
        if srv.stop.is_set():
            raise Problem("SERVER_STOPPING", "Export interrupted by server shutdown.", 503)
        if not record["current_revision"]:
            excluded.append(
                {
                    "image_id": record["image_id"],
                    "filename": record["display_filename"],
                    "reason": "UNLABELED",
                }
            )
            continue
        if not record["annotation_path"] or record["schema_id"] != schema["id"]:
            raise Problem("SCHEMA_MISMATCH", "A saved annotation is missing or uses another class schema.")
        doc = srv.blobs.json(record["annotation_path"], record["annotation_sha256"])
        expected = {
            "image_id": record["image_id"],
            "project_id": snapshot["project_id"],
            "asset_sha256": record["asset_sha256"],
            "revision": record["current_revision"],
            "width": record["width"],
            "height": record["height"],
            "class_schema_id": schema["id"],
        }
        if any(doc.get(k) != v for k, v in expected.items()):
            raise Problem("CORRUPT_BLOB", "Annotation identity does not match its captured source.", 503)
        content = validate_content(
            {k: doc[k] for k in ("shapes", "image_labels", "verified_empty")},
            record["width"],
            record["height"],
            snapshot["task_type"],
            [c["class_id"] for c in classes],
        )
        if record["status"] == "SKIPPED" or not (
            content["shapes"] or content["image_labels"] or content["verified_empty"]
        ):
            excluded.append(
                {
                    "image_id": record["image_id"],
                    "filename": record["display_filename"],
                    "reason": "INCOMPLETE_OR_SKIPPED",
                }
            )
            continue
        included.append(
            dict(
                record,
                content=content,
                class_ids=sorted(set(content["image_labels"] + [s["class_id"] for s in content["shapes"]])),
                verified_empty=content["verified_empty"],
            )
        )
    if not included:
        raise Problem(
            "EMPTY_EXPORT", "No saved labeled or verified-empty images. Save annotations before exporting."
        )
    return classes, included, excluded


def run_export(srv, user, job_id, snapshot, request_id):
    from .service import now

    archive = srv.root / "export-cache" / f"{job_id}.zip"
    archive.parent.mkdir(exist_ok=True)
    stage = archive.with_suffix(".partial")
    try:
        with srv.db.transaction() as conn:
            srv.maintain(conn, user, snapshot["project_id"])
            conn.exec_driver_sql("UPDATE jobs SET state='running',updated_at=? WHERE id=?", (now(), job_id))
        classes, items, excluded = prepare_snapshot(srv, snapshot)
        assignments, split = split_items(items, snapshot["options"])
        classification = snapshot["task_type"] == "classification"
        folders = []
        if classification:
            observed = {c for i in items for c in i["class_ids"]}
            selected = [c for c in classes if c["class_id"] in observed]
            folders = classification_mapping(selected, observed, observed)
        folder_by_class = {f["internal_class_id"]: f["folder_name"] for f in folders}
        files, outputs = [], []
        with zipfile.ZipFile(stage, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as bundle:

            def add(name, data):
                info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
                bundle.writestr(info, data)
                files.append({"path": name, "bytes": len(data), "sha256": digest(data)})

            for part in PARTITIONS:
                if split["actual_counts"][part]:
                    for folder in folder_by_class.values() if classification else ("images", "labels"):
                        name = f"{part}/{folder}/" if classification else f"{folder}/{part}/"
                        bundle.writestr(zipfile.ZipInfo(name), b"")
            for count, item in enumerate(items, 1):
                if srv.stop.is_set():
                    raise Problem("SERVER_STOPPING", "Export interrupted by server shutdown.", 503)
                raw = srv.blobs.read(item["asset_path"], item["asset_sha256"])
                if exif_orientation(raw) != 1:
                    raise Problem(
                        "ORIENTATION_AMBIGUOUS",
                        "An image has EXIF rotation. Preprocess as a new asset and relabel before training export.",
                    )
                part = assignments[item["image_id"]]
                name = f"{item['image_id']}.{item['extension']}"
                image_path = (
                    f"{part}/{folder_by_class[item['class_ids'][0]]}/{name}"
                    if classification
                    else f"images/{part}/{name}"
                )
                add(image_path, raw)
                if not classification:
                    label, _ = yolo_labels(
                        item["content"], item["width"], item["height"], snapshot["task_type"], classes
                    )
                    add(f"labels/{part}/{item['image_id']}.txt", label)
                outputs.append(
                    {
                        k: item[k]
                        for k in (
                            "image_id",
                            "display_filename",
                            "asset_sha256",
                            "annotation_sha256",
                            "current_revision",
                            "group_key",
                            "status",
                        )
                    }
                    | {"partition": part, "image_path": image_path}
                )
                with srv.db.transaction() as conn:
                    conn.exec_driver_sql(
                        "UPDATE jobs SET progress_done=?,updated_at=? WHERE id=?", (count, now(), job_id)
                    )
            if not classification:
                yaml, _ = yolo_config(classes, has_val=True, has_test=bool(split["actual_counts"]["test"]))
                add("data.yaml", yaml)
            add("prepare_dataset.py", PREPARE_SCRIPT.encode())
            task = {"detection": "detect", "segmentation": "segment", "classification": "classify"}[
                snapshot["task_type"]
            ]
            data_arg = "." if classification else "data.local.yaml"
            instruction = (
                f"VisionLabel working {task} dataset\n\n"
                "Saved annotations, including unreviewed predictions. Inspect labels before training.\n"
                "No approved release is implied. Original images are copied without rotation.\n"
                "Run: python prepare_dataset.py after moving this directory.\n"
                "In your separate Ultralytics training environment, using a local model for this task:\n"
                f'yolo {task} train model="PATH_TO_LOCAL_MODEL.pt" data="{data_arg}" epochs=100 imgsz=640\n'
                "Run from this dataset directory, or use the absolute data path.\n"
                "Classification takes the dataset directory, not a YOLO labels TXT or YAML.\n"
                "class_mapping.json maps consumer indices/folders to project classes.\n"
                "Manifest records actual split counts and all excluded images.\n"
            )
            add("TRAINING.txt", instruction.encode())
            add("class_mapping.json", canonical({"classes": classes, "classification_folders": folders}))
            manifest = {
                "profile": PROFILE,
                "task_type": snapshot["task_type"],
                "project_id": snapshot["project_id"],
                "source": "saved_working_snapshot",
                "approved_release": False,
                "format_version": FORMAT_VERSION,
                "snapshot_sha256": digest(canonical(snapshot)),
                "schema_sha256": snapshot["schema"]["sha256"],
                "split": split,
                "items": outputs,
                "excluded": excluded,
                "files": files,
            }
            bundle.writestr(zipfile.ZipInfo("manifest.json"), canonical(manifest))
        with stage.open("r+b") as stream:
            os.fsync(stream.fileno())
        archive_hash = file_hash(stage)
        srv.fault("export_before_publish")
        with srv.db.transaction() as conn:
            srv.maintain(conn, user, snapshot["project_id"])
            stage.rename(archive)
            result = {
                "sha256": archive_hash,
                "bytes": archive.stat().st_size,
                "included": len(items),
                "excluded_count": len(excluded),
                "excluded": excluded,
                "split": split,
                "task_type": snapshot["task_type"],
                "approved_release": False,
            }
            conn.exec_driver_sql(
                "UPDATE jobs SET state='succeeded',result_json=?,progress_done=progress_total,updated_at=? WHERE id=?",
                (canonical(result).decode(), now(), job_id),
            )
            srv.audit(
                conn,
                user,
                "working_export.completed",
                job_id,
                snapshot["project_id"],
                {"archive_sha256": result["sha256"], "snapshot_sha256": manifest["snapshot_sha256"]},
                request_id,
            )
    except Exception as exc:
        stage.unlink(missing_ok=True)
        archive.unlink(missing_ok=True)
        with srv.db.transaction() as conn:
            error = {
                "code": exc.code if isinstance(exc, Problem) else "EXPORT_FAILED",
                "message": exc.message
                if isinstance(exc, Problem)
                else "Export failed. Check storage and retry with a new request.",
            }
            conn.exec_driver_sql(
                "UPDATE jobs SET state='failed',error_json=?,updated_at=? WHERE id=?",
                (canonical(error).decode(), now(), job_id),
            )


def file_hash(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def export_archive(srv, user, job_id):
    with srv.db.engine.connect() as conn:
        job = row(conn, "SELECT * FROM jobs WHERE id=? AND type='working-export'", (job_id,))
        if not job:
            raise Problem("NOT_FOUND", "Export not found.", 404)
        srv.maintain(conn, user, job["project_id"])
        if job["state"] != "succeeded":
            raise Problem("EXPORT_NOT_READY", "Export is not ready.", 409)
    result = json.loads(job["result_json"])
    path = srv.root / "export-cache" / f"{job_id}.zip"
    if not path.is_file():
        raise Problem("EXPORT_EXPIRED", "Cached export is unavailable. Prepare a new export.", 410)
    if file_hash(path) != result["sha256"]:
        raise Problem("CORRUPT_EXPORT", "Export checksum verification failed.", 503)
    return path


def install_archive(archive, destination, expected_sha):
    """Verify an untrusted archive, extract privately, publish only a complete new directory."""
    destination = Path(destination).absolute()
    if destination.exists():
        raise Problem(
            "DESTINATION_EXISTS", "Choose a new destination folder; existing folders are never overwritten."
        )
    if not destination.parent.is_dir():
        raise Problem("INVALID_DESTINATION", "Choose an existing parent folder.")
    if file_hash(archive) != expected_sha:
        raise Problem("CORRUPT_EXPORT", "Downloaded archive checksum does not match.")
    with tempfile.TemporaryDirectory(prefix=".visionlabel-export-", dir=destination.parent) as folder:
        stage = Path(folder) / "dataset"
        stage.mkdir()
        with zipfile.ZipFile(archive) as bundle:
            names = bundle.namelist()
            if len({n.casefold() for n in names}) != len(names):
                raise Problem("INVALID_EXPORT", "Archive has colliding paths.")
            manifest_info = bundle.getinfo("manifest.json")
            if manifest_info.file_size > 128 * 1024 * 1024:
                raise Problem("INVALID_EXPORT", "Manifest exceeds the supported size.")
            manifest = json.loads(bundle.read("manifest.json"))
            if manifest["profile"] != PROFILE:
                raise Problem("INVALID_EXPORT", "Unsupported export profile.")
            expected = {f["path"]: f for f in manifest["files"]}
            if len(expected) != len(manifest["files"]) or set(expected) | {"manifest.json"} != {
                n for n in names if not n.endswith("/")
            }:
                raise Problem("INVALID_EXPORT", "Archive does not match its manifest.")
            for info in bundle.infolist():
                name = info.filename.rstrip("/")
                target = contained(stage, name)
                if info.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                if info.filename != "manifest.json" and info.file_size != expected[info.filename]["bytes"]:
                    raise Problem("INVALID_EXPORT", "Export size mismatch.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, target.open("xb") as out:
                    while chunk := source.read(1024 * 1024):
                        out.write(chunk)
                    out.flush()
                    os.fsync(out.fileno())
                if (
                    info.filename != "manifest.json"
                    and file_hash(target) != expected[info.filename]["sha256"]
                ):
                    raise Problem("CORRUPT_EXPORT", "Export file checksum mismatch.")
        if manifest["task_type"] != "classification":
            template = (stage / "data.yaml").read_text(encoding="utf-8")
            local = (
                "path: "
                + json.dumps(destination.as_posix(), ensure_ascii=False)
                + "\n"
                + template.split("\n", 1)[1]
            )
            (stage / "data.local.yaml").write_text(local, encoding="utf-8")
        stage.rename(destination)
    return str(destination)

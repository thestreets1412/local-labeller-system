"""Developer format diagnostics and read-only migration dry runs. No DB writes."""

import argparse
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path

from .domain import Problem, canonical, digest, valid_uuid, validate_content
from .formats import (
    FORMAT_VERSION,
    classification_mapping,
    dimensions,
    schema_mapping,
    yolo_config,
    yolo_labels,
)
from .imaging import exif_orientation, inspect_image
from .legacy import parse_labelme, parse_yolo
from .storage import contained


def read_bounded(path, limit):
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise Problem("INPUT_TOO_LARGE", "Input exceeds the size limit.")
    return data


def read_json(path):
    return json.loads(read_bounded(path, 8 * 1024 * 1024), parse_float=Decimal)


def dry_run(root, request):
    """Check each explicit source independently; failures never hide successful rows."""
    if request.get("format") not in ("labelme", "yolo-detection"):
        raise Problem("INVALID_FORMAT", "Choose labelme or yolo-detection.")
    items = request["items"]
    if not isinstance(items, list) or not 0 < len(items) <= 1000:
        raise Problem("INVALID_INPUT", "Supply between 1 and 1000 source items.")
    empty = request.get("empty_is_verified", False)
    if type(empty) is not bool:
        raise Problem("INVALID_INPUT", "empty_is_verified must be a boolean.")
    rows = []
    for ordinal, item in enumerate(items):
        row = {"item_index": ordinal, "status": "ERROR"}
        try:
            image = contained(root, item["image"], exists=True)
            row["image"] = item["image"]
            raw_image = read_bounded(image, 50 * 1024 * 1024)
            if exif_orientation(raw_image) != 1:
                raise Problem(
                    "ORIENTATION_AMBIGUOUS",
                    "Resolve EXIF orientation through explicit preprocessing and a new asset before import.",
                )
            # Decode the same captured bytes whose hash the report records.
            with tempfile.TemporaryDirectory(prefix="visionlabel-dry-run-") as folder:
                snapshot = Path(folder) / "source-image"
                snapshot.write_bytes(raw_image)
                width, height = inspect_image(snapshot)
            label_name = item.get("label")
            raw = None
            if label_name is not None:
                label = contained(root, label_name)
                if label.exists():
                    raw = read_bounded(label, 8 * 1024 * 1024)
            identity = digest(
                canonical(
                    {
                        "image": item["image"],
                        "image_sha256": digest(raw_image),
                        "label": label_name,
                        "label_sha256": digest(raw) if raw is not None else None,
                    }
                )
            )
            if request["format"] == "labelme":
                if raw is None:
                    raise Problem("MISSING_LABEL", "LabelMe JSON source is missing.")
                document = json.loads(raw, parse_float=Decimal)
                # LabelMe imagePath is relative to its JSON, but must stay inside root.
                relative_image = str(Path(label_name).parent / document["imagePath"]).replace("\\", "/")
                resolved_image = contained(root, relative_image, exists=True)
                if resolved_image.resolve() != image.resolve():
                    raise Problem(
                        "IMAGE_PATH_MISMATCH", "LabelMe imagePath does not match the selected image."
                    )
                content, state = parse_labelme(
                    document, width, height, request["task"], request["mapping"], source_identity=identity
                )
            else:
                if request["task"] != "detection":
                    raise Problem("INVALID_FORMAT", "YOLO detection import requires a detection project.")
                content, state = parse_yolo(
                    raw.decode("utf-8-sig") if raw is not None else None,
                    width,
                    height,
                    request["mapping"],
                    source_identity=identity,
                    empty_is_verified=empty,
                )
            row.update(
                status="VALID",
                proposed_state=state,
                content=content,
                width=width,
                height=height,
                image_sha256=digest(raw_image),
                source_sha256=digest(raw) if raw is not None else None,
            )
        except (Problem, OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
            row["error"] = {
                "code": exc.code if isinstance(exc, Problem) else "INVALID_SOURCE",
                "message": str(exc),
                "details": exc.details if isinstance(exc, Problem) else {},
            }
        rows.append(row)
    return {
        "artifact_kind": "migration-dry-run",
        "tool_version": FORMAT_VERSION,
        "canonical_import": False,
        "database_conflicts_checked": False,
        "options": {
            "format": request["format"],
            "task": request["task"],
            "mapping": request["mapping"],
            "empty_is_verified": empty,
            "embedded_image_data": False,
        },
        "files": rows,
        "valid_count": sum(row["status"] == "VALID" for row in rows),
        "error_count": sum(row["status"] == "ERROR" for row in rows),
    }


def export_preview(request):
    classes = request["classes"]
    task = request["task"]
    items = request["items"]
    if not isinstance(items, list) or not 0 < len(items) <= 1000:
        raise Problem("INVALID_INPUT", "Supply between 1 and 1000 preview items.")
    mapping = schema_mapping(classes)
    seen, rows, warnings = set(), [], []
    train: set[str] = set()
    evaluation: set[str] = set()
    conversion = request.get("polygon_to_bbox", False)
    if type(conversion) is not bool:
        raise Problem("INVALID_INPUT", "polygon_to_bbox must be a boolean.")
    for item in items:
        image_id = item["image_id"]
        if not valid_uuid(image_id) or image_id in seen or item["partition"] not in ("train", "val", "test"):
            raise Problem("INVALID_INPUT", "Image UUIDs must be unique and partitions valid.")
        seen.add(image_id)
        dimensions(item["width"], item["height"])
        if task == "classification":
            if conversion:
                raise Problem("INVALID_FORMAT", "Classification does not support polygon conversion.")
            content = validate_content(
                item["content"], item["width"], item["height"], task, mapping, complete=True
            )
            cid = content["image_labels"][0]
            (train if item["partition"] == "train" else evaluation).add(cid)
            rows.append({"image_id": image_id, "partition": item["partition"], "class_id": cid})
        else:
            data, losses = yolo_labels(
                item["content"],
                item["width"],
                item["height"],
                task,
                classes,
                polygon_to_bbox=conversion,
                image_id=image_id,
            )
            rows.append(
                {
                    "image_id": image_id,
                    "partition": item["partition"],
                    "label_text": data.decode("utf-8"),
                    "bytes": len(data),
                    "sha256": digest(data),
                }
            )
            warnings.extend(losses)
    result = {
        "artifact_kind": "export-format-preview",
        "tool_version": FORMAT_VERSION,
        "canonical_export": False,
        "provenance_verified": False,
        "task": task,
        "polygon_to_bbox": conversion,
        "files": sorted(rows, key=lambda row: row["image_id"]),
        "warnings": warnings,
    }
    if task == "classification":
        result["class_mapping"] = classification_mapping(classes, train, evaluation)
    else:
        config, messages = yolo_config(
            classes,
            has_val=any(item["partition"] == "val" for item in items),
            has_test=any(item["partition"] == "test" for item in items),
        )
        result["data_yaml"] = config.decode("utf-8")
        result["warnings"].extend({"code": "EMPTY_VALIDATION", "message": message} for message in messages)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Format diagnostics only. Does not import annotations or publish training datasets."
    )
    parser.add_argument("mode", choices=("export-preview", "import-dry-run"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New JSON report; never overwritten")
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    if args.mode == "import-dry-run" and args.source_root is None:
        parser.error("--source-root is required for import-dry-run")
    try:
        request = read_json(args.input)
        report = (
            dry_run(args.source_root, request) if args.mode == "import-dry-run" else export_preview(request)
        )
        data = canonical(report)
        with args.output.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        print(f"Diagnostic report only. SHA-256: {digest(data)}")
        if report.get("error_count", 0):
            parser.exit(2, "Some sources failed. Inspect the per-file report. No data was imported.\n")
    except (Problem, OSError, ValueError, KeyError, TypeError, AttributeError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()

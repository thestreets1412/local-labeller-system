"""Pure Phase 5 format primitives. Callers must separately verify release approval."""

import json
import re
from decimal import ROUND_HALF_EVEN, Decimal

from .domain import Problem, segments_intersect, valid_uuid, validate_content

FORMAT_VERSION = "vl-formats-2"
QUANTUM = Decimal("0.000000001")


def dimensions(width, height):
    if any(type(n) is not int or not 0 < n <= 40_000_000 for n in (width, height)):
        raise Problem("INVALID_DIMENSIONS", "Dimensions must be positive integer raster sizes.")
    if width * height > 40_000_000:
        raise Problem("INVALID_DIMENSIONS", "Image exceeds the 40 megapixel limit.")


def schema_mapping(classes):
    """Explicit export indices, never list positions; retain historical schema entries."""
    result = {}
    indices = set()
    for row in classes:
        cid, index = row["class_id"], row["export_index"]
        if not valid_uuid(cid) or cid in result or type(index) is not int or not 0 <= index <= 999999:
            raise Problem("INVALID_SCHEMA", "Class IDs and export indices must be valid and unique.")
        if index in indices or not isinstance(row["name"], str) or not row["name"]:
            raise Problem("INVALID_SCHEMA", "Duplicate export index or invalid class name.")
        indices.add(index)
        result[cid] = dict(row)
    if not result:
        raise Problem("INVALID_SCHEMA", "At least one class is required.")
    return result


def quantize(value):
    return value.quantize(QUANTUM, rounding=ROUND_HALF_EVEN)


def polygon_valid(points):
    """Exact Decimal checks after nine-place quantization, without six-place serialization."""
    if len(set(points)) != len(points) or any(not 0 <= v <= 1 for p in points for v in p):
        return False
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(points, points[1:] + points[:1], strict=True))
    if not area:
        return False
    for i in range(len(points)):
        for j in range(i + 1, len(points)):
            if j == i + 1 or (i == 0 and j == len(points) - 1):
                continue
            if segments_intersect(
                points[i], points[(i + 1) % len(points)], points[j], points[(j + 1) % len(points)]
            ):
                return False
    return True


def yolo_labels(
    content,
    width,
    height,
    task,
    classes,
    *,
    polygon_to_bbox=False,
    image_id=None,
    collect_errors=False,
    format_version=FORMAT_VERSION,
):
    """Return exact label bytes plus explicit loss warnings, without claiming provenance."""
    dimensions(width, height)
    if format_version not in ("vl-formats-1", FORMAT_VERSION):
        raise Problem("INVALID_FORMAT", "Unknown format version.")
    mapping = schema_mapping(classes)
    if task not in ("detection", "segmentation") or (polygon_to_bbox and task != "segmentation"):
        raise Problem("INVALID_FORMAT", "Unsupported task or conversion option.")
    data = validate_content(content, width, height, task, mapping, complete=True)
    rows, warnings, issues = [], [], []
    geometry: dict[str, object]
    for ordinal, shape in enumerate(data["shapes"], 1):
        index = mapping[shape["class_id"]]["export_index"]
        if task == "detection" or polygon_to_bbox:
            if polygon_to_bbox:
                xs, ys = zip(*shape["points"], strict=True)
                raw = min(xs), min(ys), max(xs), max(ys)
                warnings.append(
                    {"code": "POLYGON_TO_BBOX_LOSS", "image_id": image_id, "shape_id": shape["id"]}
                )
            else:
                raw = tuple(shape[k] for k in ("x1", "y1", "x2", "y2"))
            x1, y1, x2, y2 = map(lambda x: Decimal(str(x)), raw)
            values = [
                quantize(v)
                for v in (
                    (x1 + x2) / (2 * width),
                    (y1 + y2) / (2 * height),
                    (x2 - x1) / width,
                    (y2 - y1) / height,
                )
            ]
            cx, cy, w, h = values
            if format_version == "vl-formats-2":
                # Keep nine-place centers and shrink only a rounding overshoot.
                # Each size changes by at most one quantum; zero remains an error.
                w = min(w, 2 * cx, 2 * (1 - cx))
                h = min(h, 2 * cy, 2 * (1 - cy))
                values = [cx, cy, w, h]
            valid = (
                w > 0 and h > 0 and 0 <= cx - w / 2 < cx + w / 2 <= 1 and 0 <= cy - h / 2 < cy + h / 2 <= 1
            )
            checks = {
                "WIDTH_NOT_POSITIVE": w > 0,
                "HEIGHT_NOT_POSITIVE": h > 0,
                "LEFT_OUT_OF_BOUNDS": cx - w / 2 >= 0,
                "RIGHT_OUT_OF_BOUNDS": cx + w / 2 <= 1,
                "TOP_OUT_OF_BOUNDS": cy - h / 2 >= 0,
                "BOTTOM_OUT_OF_BOUNDS": cy + h / 2 <= 1,
            }
            geometry = {
                "source": {k: str(v) for k, v in zip(("x1", "y1", "x2", "y2"), raw, strict=True)},
                "quantized": {k: str(v) for k, v in zip(("cx", "cy", "w", "h"), values, strict=True)},
                "edges": {
                    k: str(v)
                    for k, v in zip(
                        ("left", "top", "right", "bottom"),
                        (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2),
                        strict=True,
                    )
                },
            }
        else:
            points = [
                (quantize(Decimal(str(x)) / width), quantize(Decimal(str(y)) / height))
                for x, y in shape["points"]
            ]
            valid = polygon_valid(points)
            values = [v for point in points for v in point]
            checks = {"POLYGON_INVALID_AFTER_QUANTIZATION": valid}
            geometry = {
                "source_points": [[str(x), str(y)] for x, y in shape["points"]],
                "quantized_points": [[str(x), str(y)] for x, y in points],
            }
        if not valid:
            if collect_errors:
                issues.append(
                    {
                        "code": "UNREPRESENTABLE_GEOMETRY",
                        "image_id": image_id,
                        "shape_id": shape["id"],
                        "shape_number": ordinal,
                        "class_id": shape["class_id"],
                        "class_name": mapping[shape["class_id"]]["name"],
                        "export_index": index,
                        "width": width,
                        "height": height,
                        "failed_checks": [name for name, passed in checks.items() if not passed],
                        **geometry,
                    }
                )
                continue
            raise Problem(
                "UNREPRESENTABLE_GEOMETRY",
                "Geometry is invalid after nine-decimal quantization.",
                image_id=image_id,
                shape_id=shape["id"],
            )
        rows.append(str(index) + " " + " ".join(format(v, ".9f") for v in values) + "\n")
    if issues:
        raise Problem(
            "UNREPRESENTABLE_GEOMETRY",
            "Geometry is invalid after nine-decimal quantization.",
            image_id=image_id,
            issues=issues,
        )
    return "".join(rows).encode("utf-8"), warnings


def classification_mapping(classes, train_ids, evaluation_ids):
    mapping = schema_mapping(classes)
    train, evaluation = set(train_ids), set(evaluation_ids)
    if (train | evaluation) - mapping.keys():
        raise Problem("INVALID_SCHEMA", "Unknown class in split assignments.")
    if evaluation - train:
        raise Problem(
            "TRAIN_COVERAGE",
            "Every evaluation class must occur in training.",
            class_ids=sorted(evaluation - train),
        )
    width = max(4, len(str(max(row["export_index"] for row in mapping.values()))))
    result: list[dict] = []
    for cid, row in sorted(mapping.items(), key=lambda item: item[1]["export_index"]):
        # Stable key is required; a mutable display name is never used as fallback.
        key = row.get("key")
        if not isinstance(key, str) or not key:
            raise Problem("INVALID_SCHEMA", "Classification requires a stable class key.")
        safe = re.sub(r"[^a-z0-9_-]+", "_", key.casefold()).strip("_-")[:80] or "class"
        folder = f"{row['export_index']:0{width}d}_{safe}"
        result.append(
            {
                "folder_name": folder,
                "internal_class_id": cid,
                "schema_export_index": row.get("schema_export_index", row["export_index"]),
                "consumer_order": len(result),
                **({"model_export_index": row["export_index"]} if "schema_export_index" in row else {}),
            }
        )
    return result


def yolo_config(classes, *, has_val=True, has_test=True):
    mapping = schema_mapping(classes)
    indices = {row["export_index"] for row in mapping.values()}
    if indices != set(range(max(indices) + 1)):
        raise Problem(
            "INCOMPLETE_SCHEMA",
            "YOLO names require every historical slot from zero through the maximum index, including inactive classes.",
        )
    rows = ["path: .", "train: images/train"]
    if has_val:
        rows.append("val: images/val")
    if has_test:
        rows.append("test: images/test")
    rows.append("names:")
    for row in sorted(mapping.values(), key=lambda r: r["export_index"]):
        # JSON quoted strings are a YAML subset; prevent colon/newline injection.
        rows.append(f"  {row['export_index']}: {json.dumps(row['name'], ensure_ascii=False)}")
    return ("\n".join(rows) + "\n").encode("utf-8"), (
        [] if has_val else ["Validation partition is empty; training consumers may require it."]
    )

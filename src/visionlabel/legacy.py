"""Legacy syntax conversion only; never writes canonical annotations or approvals."""

import re
from decimal import Decimal, InvalidOperation
from uuid import UUID, uuid5

from .domain import Problem, empty_content, valid_uuid, validate_content
from .formats import dimensions

NAMESPACE = UUID("c6d801cd-63f2-4d7b-a431-83232248e5db")


def shape_id(source_identity, ordinal):
    return str(uuid5(NAMESPACE, f"{source_identity}:{ordinal}"))


def check_mapping(mapping):
    if not isinstance(mapping, dict) or not mapping or any(not valid_uuid(v) for v in mapping.values()):
        raise Problem("INVALID_MAPPING", "An explicit source label to class UUID mapping is required.")


def parse_yolo(text, width, height, mapping, *, source_identity, empty_is_verified=False):
    dimensions(width, height)
    check_mapping(mapping)
    data = empty_content()
    if text is None:
        return data, "UNLABELED"
    if not text.strip():
        data["verified_empty"] = empty_is_verified
        return data, "ANNOTATED" if empty_is_verified else "UNLABELED"
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        fields = line.split()
        if len(fields) != 5 or not re.fullmatch(r"0|[1-9][0-9]*", fields[0]) or fields[0] not in mapping:
            raise Problem(
                "INVALID_YOLO",
                "Expected a mapped integer class and exactly four coordinates.",
                line=line_number,
            )
        try:
            cx, cy, w, h = [Decimal(v) for v in fields[1:]]
            if any(not v.is_finite() or not 0 <= v <= 1 for v in (cx, cy, w, h)):
                raise ValueError
            if not (
                w > 0 and h > 0 and 0 <= cx - w / 2 < cx + w / 2 <= 1 and 0 <= cy - h / 2 < cy + h / 2 <= 1
            ):
                raise ValueError
        except (InvalidOperation, ValueError):
            raise Problem(
                "INVALID_YOLO",
                "Coordinates must be finite, positive-area and inside the raster.",
                line=line_number,
            ) from None
        data["shapes"].append(
            {
                "id": shape_id(source_identity, line_number),
                "type": "rectangle",
                "class_id": mapping[fields[0]],
                "attributes": {},
                "x1": (cx - w / 2) * width,
                "y1": (cy - h / 2) * height,
                "x2": (cx + w / 2) * width,
                "y2": (cy + h / 2) * height,
            }
        )
    return validate_content(
        data, width, height, "detection", set(mapping.values()), complete=True
    ), "ANNOTATED"


def parse_labelme(document, width, height, task, mapping, *, source_identity):
    dimensions(width, height)
    check_mapping(mapping)
    if set(document) - {"version", "flags", "shapes", "imagePath", "imageData", "imageHeight", "imageWidth"}:
        raise Problem(
            "UNSUPPORTED_METADATA", "Unknown LabelMe document fields require explicit migration support."
        )
    if task not in ("detection", "segmentation"):
        raise Problem("INVALID_FORMAT", "LabelMe supports detection or segmentation imports.")
    if document.get("imageData"):
        raise Problem("EMBEDDED_IMAGE_DISABLED", "Embedded imageData is disabled; supply an external image.")
    if document.get("imageWidth") != width or document.get("imageHeight") != height:
        raise Problem("DIMENSION_MISMATCH", "LabelMe dimensions do not match the decoded raw raster.")
    if document.get("flags"):
        raise Problem("UNSUPPORTED_METADATA", "LabelMe image flags require explicit migration support.")
    shapes = document.get("shapes")
    if not isinstance(shapes, list) or len(shapes) > 10000:
        raise Problem("INVALID_LABELME", "Expected an array of at most 10000 shapes.")
    data = empty_content()
    for index, shape in enumerate(shapes):
        if not isinstance(shape, dict):
            raise Problem("INVALID_LABELME", "Each shape must be an object.", shape_index=index)
        if set(shape) - {"label", "points", "group_id", "shape_type", "flags", "description"}:
            raise Problem(
                "UNSUPPORTED_METADATA",
                "Unknown shape fields require explicit migration support.",
                shape_index=index,
            )
        expected = "rectangle" if task == "detection" else "polygon"
        if shape.get("shape_type") != expected:
            raise Problem(
                "UNSUPPORTED_SHAPE", "Shape type does not match the project task.", shape_index=index
            )
        if shape.get("flags") or shape.get("group_id") is not None or shape.get("description"):
            raise Problem(
                "UNSUPPORTED_METADATA",
                "Shape flags, groups and descriptions require explicit migration support.",
                shape_index=index,
            )
        label = shape.get("label")
        if not isinstance(label, str) or label not in mapping:
            raise Problem(
                "UNMAPPED_LABEL", "Every label must have an explicit class mapping.", shape_index=index
            )
        points = shape.get("points")
        if not isinstance(points, list) or any(
            not isinstance(p, list) or len(p) != 2 or any(type(v) not in (int, float, Decimal) for v in p)
            for p in points
        ):
            raise Problem("INVALID_LABELME", "Invalid point coordinates.", shape_index=index)
        converted = {
            "id": shape_id(source_identity, index),
            "type": expected,
            "class_id": mapping[label],
            "attributes": {},
        }
        if expected == "rectangle":
            if len(points) != 2:
                raise Problem("INVALID_LABELME", "Rectangles require exactly two points.", shape_index=index)
            xs, ys = zip(*points, strict=True)
            converted.update(x1=min(xs), y1=min(ys), x2=max(xs), y2=max(ys))
        else:
            converted["points"] = points
        data["shapes"].append(converted)
    return validate_content(
        data, width, height, task, set(mapping.values())
    ), "ANNOTATED" if shapes else "UNLABELED"

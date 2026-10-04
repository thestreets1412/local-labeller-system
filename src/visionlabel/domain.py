"""Pure geometry, serialization and local editing; no GUI/HTTP/ORM imports."""

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal
from uuid import UUID, uuid4


class Problem(Exception):
    def __init__(self, code: str, message: str, status: int = 422, **details):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(value) -> bytes:
    def encode(item):
        if item is None:
            return "null"
        if isinstance(item, bool):
            return "true" if item else "false"
        if isinstance(item, str):
            return json.dumps(item, ensure_ascii=False)
        if isinstance(item, int):
            return str(item)
        if isinstance(item, (float, Decimal)):
            number = Decimal(str(item))
            if not number.is_finite() or abs(number) > Decimal("1e20"):
                raise Problem("VALIDATION_FAILED", "Number is not finite or exceeds the supported range.")
            number = number.quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
            if not number:
                return "0"
            return format(number, "f").rstrip("0").rstrip(".") if number % 1 else str(int(number))
        if isinstance(item, list):
            return "[" + ",".join(encode(x) for x in item) + "]"
        if isinstance(item, dict):
            return "{" + ",".join(encode(k) + ":" + encode(item[k]) for k in sorted(item)) + "}"
        raise Problem("VALIDATION_FAILED", "Unsupported JSON value.")

    return encode(value).encode("utf-8")


def uid() -> str:
    return str(uuid4())


def valid_uuid(value):
    try:
        return str(UUID(value)) == value
    except (ValueError, TypeError, AttributeError):
        return False


def empty_content():
    return {"verified_empty": False, "image_labels": [], "shapes": []}


def validate_content(content, width, height, task, class_ids, complete=False):
    data = json.loads(canonical(content))
    if set(data) != {"verified_empty", "image_labels", "shapes"}:
        raise Problem("VALIDATION_FAILED", "Unexpected annotation fields.")
    labels, shapes = data["image_labels"], data["shapes"]
    if (
        type(data["verified_empty"]) is not bool
        or not isinstance(labels, list)
        or not isinstance(shapes, list)
    ):
        raise Problem("VALIDATION_FAILED", "Invalid annotation content.")
    if len(shapes) > 10000 or len(labels) > 1:
        raise Problem("VALIDATION_FAILED", "Annotation exceeds task limits.")
    if len(set(labels)) != len(labels) or any(x not in class_ids for x in labels):
        raise Problem("VALIDATION_FAILED", "Unknown or duplicate image label.")
    if data["verified_empty"] and (labels or shapes):
        raise Problem("VALIDATION_FAILED", "Verified-empty images cannot contain labels.")
    if task == "classification":
        if shapes or data["verified_empty"] or (complete and len(labels) != 1):
            raise Problem("VALIDATION_FAILED", "Classification requires one image label and no shapes.")
    elif task in ("detection", "segmentation"):
        if labels or (complete and not shapes and not data["verified_empty"]):
            raise Problem("VALIDATION_FAILED", "Add a shape or explicitly mark the image verified empty.")
    else:
        raise Problem("VALIDATION_FAILED", "Unsupported task type.")
    seen = set()
    vertices = 0
    for index, shape in enumerate(shapes):

        def invalid(message, index=index):
            raise Problem("VALIDATION_FAILED", message, path=f"content.shapes[{index}]")

        if not isinstance(shape, dict):
            invalid("Each shape must be an object.")
        if not valid_uuid(shape.get("id")) or shape["id"] in seen:
            invalid("Shape IDs must be unique UUIDs.")
        seen.add(shape["id"])
        if not isinstance(shape.get("class_id"), str) or shape.get("class_id") not in class_ids:
            invalid("Unknown or inactive class.")
        attrs = shape.get("attributes")
        if not isinstance(attrs, dict) or attrs:
            invalid("This project has no enabled attribute extensions.")
        if task == "detection":
            if set(shape) != {"id", "type", "class_id", "x1", "y1", "x2", "y2", "attributes"}:
                invalid("Unexpected rectangle fields.")
            if shape["type"] != "rectangle":
                invalid("Detection only supports rectangles.")
            coords = [shape[k] for k in ("x1", "y1", "x2", "y2")]
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in coords):
                invalid("Coordinates must be finite numbers.")
            x1, y1, x2, y2 = coords
            if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
                invalid("Rectangle must have positive area and remain inside the image.")
        elif task == "segmentation":
            if set(shape) != {"id", "type", "class_id", "points", "attributes"} or shape["type"] != "polygon":
                invalid("Segmentation only supports polygons.")
            pts = shape["points"]
            if not isinstance(pts, list):
                invalid("Polygon points must be an array.")
            vertices += len(pts)
            if len(pts) < 3 or vertices > 10000:
                invalid("Invalid polygon vertex count.")
            if any(
                not isinstance(p, list) or len(p) != 2 or any(type(v) not in (int, float) for v in p)
                for p in pts
            ):
                invalid("Invalid polygon coordinates.")
            if any(not (0 <= x <= width and 0 <= y <= height) for x, y in pts):
                invalid("Polygon lies outside image bounds.")
            if len({tuple(p) for p in pts}) != len(pts):
                invalid("Repeated polygon vertex.")
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True))
            if not area:
                invalid("Polygon has zero area.")
            for i in range(len(pts)):
                for j in range(i + 1, len(pts)):
                    if j == i + 1 or (i == 0 and j == len(pts) - 1):
                        continue
                    if segments_intersect(pts[i], pts[(i + 1) % len(pts)], pts[j], pts[(j + 1) % len(pts)]):
                        invalid("Polygon self-intersects.")
            if area < 0:
                pts.reverse()
            start = min(range(len(pts)), key=lambda n: tuple(pts[n]))
            shape["points"] = pts[start:] + pts[:start]
    shapes.sort(key=lambda s: s["id"])
    labels.sort()
    return data


def segments_intersect(a, b, c, d):
    def cross(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on(p, q, r):
        return min(p[0], q[0]) <= r[0] <= max(p[0], q[0]) and min(p[1], q[1]) <= r[1] <= max(p[1], q[1])

    u, v, w, z = cross(a, b, c), cross(a, b, d), cross(c, d, a), cross(c, d, b)
    return (u * v < 0 and w * z < 0) or any(
        (s == 0 and on(p, q, r)) for s, p, q, r in [(u, a, b, c), (v, a, b, d), (w, c, d, a), (z, c, d, b)]
    )


@dataclass
class Transform:
    scale: float = 1
    ox: float = 0
    oy: float = 0

    def screen(self, x, y):
        return x * self.scale + self.ox, y * self.scale + self.oy

    def pixel(self, x, y):
        return (x - self.ox) / self.scale, (y - self.oy) / self.scale

    def zoom(self, x, y, factor):
        px, py = self.pixel(x, y)
        self.scale = min(32, max(0.01, self.scale * factor))
        self.ox, self.oy = x - px * self.scale, y - py * self.scale

    def fit(self, width, height, viewport_width, viewport_height):
        self.scale = min((viewport_width - 24) / width, (viewport_height - 24) / height)
        self.ox, self.oy = (
            (viewport_width - width * self.scale) / 2,
            (viewport_height - height * self.scale) / 2,
        )


class Editor:
    def __init__(self):
        self.content = empty_content()
        self.undo_stack: list[dict] = []
        self.redo_stack: list[dict] = []
        self.saved = canonical(self.content)
        self.selected = None

    @property
    def dirty(self):
        return canonical(self.content) != self.saved

    def load(self, content):
        self.content = copy.deepcopy(content)
        self.saved = canonical(content)
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.selected = None

    def change(self, content):
        if content != self.content:
            self.undo_stack.append(copy.deepcopy(self.content))
            self.undo_stack = self.undo_stack[-100:]
            self.redo_stack.clear()
            self.content = copy.deepcopy(content)

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.content)
            self.content = self.undo_stack.pop()

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.content)
            self.content = self.redo_stack.pop()

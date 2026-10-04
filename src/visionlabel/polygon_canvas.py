"""Simple-polygon interaction in original raster coordinates."""

import copy
import math

from .canvas import Canvas
from .domain import Problem, uid, validate_content


def inside_polygon(x, y, points):
    inside = False
    for a, b in zip(points, points[1:] + points[:1], strict=True):
        # Include the boundary as selectable.
        if segment_distance(x, y, a, b) <= 1e-7:
            return True
        if (a[1] > y) != (b[1] > y):
            crossing = a[0] + (y - a[1]) * (b[0] - a[0]) / (b[1] - a[1])
            if x < crossing:
                inside = not inside
    return inside


def segment_distance(x, y, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = dx * dx + dy * dy
    ratio = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / length)) if length else 0
    return math.hypot(x - a[0] - ratio * dx, y - a[1] - ratio * dy)


class PolygonCanvas(Canvas):
    def __init__(self, editor):
        super().__init__(editor)
        self.mode = "polygon"
        self.draft: list[list[float]] = []
        self.draft_class: str | None = None
        self.hover: tuple[float, float] | None = None
        self.selected_vertex: int | None = None

    def handles(self, shape):
        return shape["points"]

    def validated(self, data):
        classes = {s["class_id"] for s in data["shapes"]}
        return validate_content(data, self.width, self.height, "segmentation", classes)

    def start(self, sx, sy, class_id, pan=False):
        if pan:
            super().start(sx, sy, class_id, pan=True)
            return
        x, y = self.transform.pixel(sx, sy)
        if not (0 <= x <= self.width and 0 <= y <= self.height):
            return
        if self.mode == "polygon":
            if not class_id:
                return
            if self.draft and len(self.draft) >= 3:
                fx, fy = self.transform.screen(*self.draft[0])
                if math.hypot(fx - sx, fy - sy) <= 7:
                    self.finish_polygon()
                    return
            if self.draft:
                lx, ly = self.transform.screen(*self.draft[-1])
                if math.hypot(lx - sx, ly - sy) < 2:
                    return  # The second click of a double-click is not another vertex.
            if len(self.draft) + sum(len(s["points"]) for s in self.editor.content["shapes"]) >= 10000:
                raise Problem("VALIDATION_FAILED", "An image may contain at most 10,000 polygon vertices.")
            if not self.draft:
                self.draft_class = class_id
                self.selected_vertex = None
                self.editor.selected = None
            self.draft.append([x, y])
            self.hover = (x, y)
            return
        self.selected_vertex = None
        snapshot = copy.deepcopy(self.editor.content)
        selected = next((s for s in snapshot["shapes"] if s["id"] == self.editor.selected), None)
        if selected:
            for index, point in enumerate(selected["points"]):
                hx, hy = self.transform.screen(*point)
                if math.hypot(hx - sx, hy - sy) <= 7:
                    self.selected_vertex = index
                    self.gesture = {"kind": "vertex", "shape": selected, "base": snapshot, "index": index}
                    self.preview = snapshot
                    return
        hit = next((s for s in reversed(snapshot["shapes"]) if inside_polygon(x, y, s["points"])), None)
        self.editor.selected = hit["id"] if hit else None
        if hit:
            self.gesture = {
                "kind": "polygon_move",
                "shape": copy.deepcopy(hit),
                "base": snapshot,
                "start": (x, y),
            }
            self.preview = snapshot

    def move(self, sx, sy):
        self.hover = self.bound(*self.transform.pixel(sx, sy))
        g = self.gesture
        if not g:
            return
        if g["kind"] == "pan":
            super().move(sx, sy)
            return
        assert self.hover is not None
        x, y = self.hover
        data = copy.deepcopy(g["base"])
        shape = next(s for s in data["shapes"] if s["id"] == g["shape"]["id"])
        if g["kind"] == "vertex":
            shape["points"][g["index"]] = [x, y]
        else:
            points = g["shape"]["points"]
            dx = max(
                -min(p[0] for p in points), min(self.width - max(p[0] for p in points), x - g["start"][0])
            )
            dy = max(
                -min(p[1] for p in points), min(self.height - max(p[1] for p in points), y - g["start"][1])
            )
            shape["points"] = [[p[0] + dx, p[1] + dy] for p in points]
        self.preview = data

    def finish(self):
        data, g = self.preview, self.gesture
        self.gesture = self.preview = None
        if data:
            selected_point = None
            if g and g["kind"] == "vertex":
                selected_point = next(s for s in data["shapes"] if s["id"] == self.editor.selected)["points"][
                    g["index"]
                ]
            normalized = self.validated(data)
            self.editor.change(normalized)
            if selected_point is not None:
                shape = next(s for s in normalized["shapes"] if s["id"] == self.editor.selected)
                # Normalization can rotate/reverse the vertex order.
                self.selected_vertex = min(
                    range(len(shape["points"])), key=lambda i: math.dist(shape["points"][i], selected_point)
                )

    def finish_polygon(self):
        if not self.draft:
            return
        data = copy.deepcopy(self.editor.content)
        ident = uid()
        data["shapes"].append(
            {
                "id": ident,
                "type": "polygon",
                "class_id": self.draft_class,
                "points": copy.deepcopy(self.draft),
                "attributes": {},
            }
        )
        data["verified_empty"] = False
        # Validation errors keep the unfinished points available for correction.
        normalized = self.validated(data)
        self.editor.change(normalized)
        self.editor.selected = ident
        self.draft = []
        self.draft_class = None
        self.hover = None
        self.selected_vertex = None

    def insert_vertex(self, sx, sy):
        self.gesture = self.preview = None
        shape = next((s for s in self.editor.content["shapes"] if s["id"] == self.editor.selected), None)
        if not shape:
            return
        points = shape["points"]
        edges = list(zip(points, points[1:] + points[:1], strict=True))
        distances = [
            segment_distance(sx, sy, self.transform.screen(*a), self.transform.screen(*b)) for a, b in edges
        ]
        index = min(range(len(edges)), key=distances.__getitem__)
        if distances[index] > 7:
            return
        x, y = self.bound(*self.transform.pixel(sx, sy))
        a, b = edges[index]
        dx, dy = b[0] - a[0], b[1] - a[1]
        ratio = max(0, min(1, ((x - a[0]) * dx + (y - a[1]) * dy) / (dx * dx + dy * dy)))
        point = [a[0] + ratio * dx, a[1] + ratio * dy]
        data = copy.deepcopy(self.editor.content)
        target = next(s for s in data["shapes"] if s["id"] == shape["id"])
        target["points"].insert(index + 1, point)
        self.editor.change(self.validated(data))
        self.selected_vertex = None

    def delete_vertex(self):
        if self.selected_vertex is None:
            return False
        data = copy.deepcopy(self.editor.content)
        shape = next((s for s in data["shapes"] if s["id"] == self.editor.selected), None)
        if not shape or self.selected_vertex >= len(shape["points"]):
            self.selected_vertex = None
            return False
        if len(shape["points"]) == 3:
            raise Problem(
                "VALIDATION_FAILED", "A polygon needs at least three vertices. Use Delete shape to remove it."
            )
        del shape["points"][self.selected_vertex]
        self.editor.change(self.validated(data))
        self.selected_vertex = None
        return True

    def cancel(self):
        super().cancel()
        self.draft = []
        self.draft_class = None
        self.hover = None
        self.selected_vertex = None

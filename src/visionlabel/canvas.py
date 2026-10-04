"""Testable pointer gestures in original image coordinates."""

import copy
from typing import Any

from .domain import Editor, Transform, uid


class Canvas:
    def __init__(self, editor: Editor):
        self.editor = editor
        self.transform = Transform()
        self.width, self.height = 1, 1
        self.mode = "rectangle"
        self.gesture: dict[str, Any] | None = None
        self.preview: dict[str, Any] | None = None

    def bound(self, x, y):
        return max(0, min(self.width, x)), max(0, min(self.height, y))

    def handles(self, shape):
        x1, y1, x2, y2 = [shape[k] for k in ("x1", "y1", "x2", "y2")]
        return [
            (x1, y1),
            ((x1 + x2) / 2, y1),
            (x2, y1),
            (x2, (y1 + y2) / 2),
            (x2, y2),
            ((x1 + x2) / 2, y2),
            (x1, y2),
            (x1, (y1 + y2) / 2),
        ]

    def start(self, sx, sy, class_id, pan=False):
        if pan:
            self.gesture = {
                "kind": "pan",
                "screen": (sx, sy),
                "offset": (self.transform.ox, self.transform.oy),
            }
            return
        px, py = self.transform.pixel(sx, sy)
        if not (0 <= px <= self.width and 0 <= py <= self.height):
            return
        snapshot = copy.deepcopy(self.editor.content)
        selected = next((s for s in snapshot["shapes"] if s["id"] == self.editor.selected), None)
        if selected:
            for i, (x, y) in enumerate(self.handles(selected)):
                hx, hy = self.transform.screen(x, y)
                if abs(hx - sx) <= 7 and abs(hy - sy) <= 7:
                    self.gesture = {
                        "kind": "resize",
                        "handle": i,
                        "shape": selected,
                        "base": snapshot,
                        "start": (px, py),
                    }
                    self.preview = snapshot
                    return
        if self.mode == "select":
            hit = next(
                (
                    s
                    for s in reversed(snapshot["shapes"])
                    if s["x1"] <= px <= s["x2"] and s["y1"] <= py <= s["y2"]
                ),
                None,
            )
            self.editor.selected = hit["id"] if hit else None
            if hit:
                self.gesture = {
                    "kind": "move",
                    "shape": copy.deepcopy(hit),
                    "base": snapshot,
                    "start": (px, py),
                }
                self.preview = snapshot
            return
        if class_id:
            self.gesture = {
                "kind": "create",
                "base": snapshot,
                "start": (px, py),
                "class_id": class_id,
                "id": uid(),
            }
            self.preview = snapshot

    def move(self, sx, sy):
        g = self.gesture
        if not g:
            return
        if g["kind"] == "pan":
            self.transform.ox = g["offset"][0] + sx - g["screen"][0]
            self.transform.oy = g["offset"][1] + sy - g["screen"][1]
            return
        x, y = self.bound(*self.transform.pixel(sx, sy))
        data = copy.deepcopy(g["base"])
        if g["kind"] == "create":
            x1, y1 = g["start"]
            shape = {
                "id": g["id"],
                "type": "rectangle",
                "class_id": g["class_id"],
                "x1": min(x, x1),
                "y1": min(y, y1),
                "x2": max(x, x1),
                "y2": max(y, y1),
                "attributes": {},
            }
            data["shapes"].append(shape)
            data["verified_empty"] = False
            self.editor.selected = shape["id"]
        else:
            shape = next(s for s in data["shapes"] if s["id"] == g["shape"]["id"])
            original = g["shape"]
            if g["kind"] == "move":
                dx = max(-original["x1"], min(self.width - original["x2"], x - g["start"][0]))
                dy = max(-original["y1"], min(self.height - original["y2"], y - g["start"][1]))
                for key in ("x1", "x2"):
                    shape[key] = original[key] + dx
                for key in ("y1", "y2"):
                    shape[key] = original[key] + dy
            else:
                handle = g["handle"]
                if handle in (0, 6, 7):
                    shape["x1"] = x
                if handle in (2, 3, 4):
                    shape["x2"] = x
                if handle in (0, 1, 2):
                    shape["y1"] = y
                if handle in (4, 5, 6):
                    shape["y2"] = y
                shape["x1"], shape["x2"] = sorted((shape["x1"], shape["x2"]))
                shape["y1"], shape["y2"] = sorted((shape["y1"], shape["y2"]))
        self.preview = data

    def finish(self):
        data = self.preview
        self.gesture = self.preview = None
        if data and all(
            s["x2"] - s["x1"] >= 0.000001 and s["y2"] - s["y1"] >= 0.000001 for s in data["shapes"]
        ):
            self.editor.change(data)

    def cancel(self):
        self.gesture = self.preview = None

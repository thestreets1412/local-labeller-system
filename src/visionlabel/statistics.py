"""Deterministic working-set counts from a captured set of immutable annotations."""

from collections import Counter


def summarize(images, entries):
    by_class = {
        e["class_id"]: {
            "class_id": e["class_id"],
            "display_name": e["display_name"],
            "image_count": 0,
            "object_count": 0,
        }
        for e in entries
    }
    statuses: Counter = Counter()
    formats: Counter = Counter()
    resolutions: Counter = Counter()
    groups: Counter = Counter()
    warnings = []
    empty = 0
    for image, annotation in images:
        statuses[image["status"]] += 1
        formats[image["media_type"]] += 1
        resolutions[f"{image['width']}x{image['height']}"] += 1
        groups[image["group_key"] or "(ungrouped)"] += 1
        base = {"image_id": image["id"], "filename": image["display_filename"]}
        if annotation is None or not (
            annotation["shapes"] or annotation["image_labels"] or annotation["verified_empty"]
        ):
            warnings.append(
                dict(base, code="UNLABELED", message="No saved label or verified-empty confirmation.")
            )
        if not image["group_key"]:
            warnings.append(
                dict(
                    base,
                    code="MISSING_GROUP",
                    message="No group is assigned; review related images before splitting.",
                )
            )
        if annotation is None:
            continue
        empty += int(annotation["verified_empty"])
        presence = set(annotation["image_labels"])
        for shape in annotation["shapes"]:
            presence.add(shape["class_id"])
            by_class[shape["class_id"]]["object_count"] += 1
            if shape["type"] == "rectangle":
                tiny = shape["x2"] - shape["x1"] < 2 or shape["y2"] - shape["y1"] < 2
            else:
                pts = shape["points"]
                twice_area = sum(
                    a[0] * b[1] - b[0] * a[1] for a, b in zip(pts, pts[1:] + pts[:1], strict=True)
                )
                tiny = abs(twice_area) < 8
            if tiny:
                warnings.append(
                    dict(
                        base,
                        shape_id=shape["id"],
                        code="TINY_SHAPE",
                        message="Very small geometry; inspect before review.",
                    )
                )
        for class_id in presence:
            by_class[class_id]["image_count"] += 1
    counts = [c["image_count"] for c in by_class.values()]
    return {
        "total_images": len(images),
        "approved_images": statuses["APPROVED"],
        "verified_empty_images": empty,
        "status_counts": dict(sorted(statuses.items())),
        "classes": sorted(by_class.values(), key=lambda c: c["class_id"]),
        "class_imbalance": {
            "min_image_count": min(counts, default=0),
            "max_image_count": max(counts, default=0),
            "classes_without_images": sorted(k for k, v in by_class.items() if not v["image_count"]),
        },
        "groups": dict(sorted(groups.items())),
        "formats": dict(sorted(formats.items())),
        "resolutions": dict(sorted(resolutions.items())),
        "warnings": warnings,
    }

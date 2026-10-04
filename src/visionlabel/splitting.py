"""Deterministic split planning. No DB, GUI, IO or global random state.

Inputs are validated, normalized projections supplied by an adapter. The engine
does not assert that a projection came from an authenticated released version.
All optimization and threshold decisions use exact rational arithmetic.
"""

from collections import Counter
from fractions import Fraction
from math import lcm
from typing import Any

from .domain import canonical, digest

PARTITIONS = ("train", "val", "test")
BPS = 10000


def targets(total, ratios):
    result = {p: total * ratios[p] // BPS for p in PARTITIONS}
    order = sorted(PARTITIONS, key=lambda p: (-(total * ratios[p] % BPS), PARTITIONS.index(p)))
    for part in order[: total - sum(result.values())]:
        result[part] += 1
    return result


def effective_groups(items, use_groups):
    parent = {item["image_id"]: item["image_id"] for item in items}

    def find(ident):
        while parent[ident] != ident:
            parent[ident] = parent[parent[ident]]
            ident = parent[ident]
        return ident

    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)

    assets: dict[str, str] = {}
    keys: dict[str, str] = {}
    for item in items:
        ident, sha, key = item["image_id"], item["asset_sha256"], item["group_key"]
        if sha in assets:
            union(ident, assets[sha])
        assets[sha] = ident
        if use_groups and key is not None:
            if key in keys:
                union(ident, keys[key])
            keys[key] = ident
    members: dict[str, list] = {}
    for item in items:
        members.setdefault(find(item["image_id"]), []).append(item)
    result = []
    for ident in sorted(members):
        images = sorted(members[ident], key=lambda item: item["image_id"])
        labels: Counter = Counter()
        for item in images:
            labels.update(item["class_ids"] or ["__empty__"])
        result.append(
            {
                "id": ident,
                "key": digest(canonical([i["image_id"] for i in images])),
                "items": images,
                "size": len(images),
                "classes": labels,
            }
        )
    return result


def plan_split(source, config):
    items = source["items"]
    ratios = config["ratios_bps"]
    active = [p for p in PARTITIONS if ratios[p]]
    grouped = config["strategy"] in ("group", "stratified_group")
    stratified = config["strategy"] in ("stratified", "stratified_group")
    groups = effective_groups(items, grouped)
    total = len(items)
    totals: Counter = Counter()
    for group in groups:
        totals.update(group["classes"])
    class_count = len(totals)
    common = lcm(total**2, *(n**2 * class_count for n in totals.values())) if stratified else total**2
    size_weight = common // total**2
    class_weights = {cls: common // (n**2 * class_count) for cls, n in totals.items()} if stratified else {}
    image_targets = targets(total, ratios)
    warnings: list[dict[str, Any]] = []
    violations = []
    assignments: dict[str, str] = {}
    sizes = {p: 0 for p in PARTITIONS}
    counts: dict[str, Counter[str]] = {p: Counter() for p in PARTITIONS}
    group_counts = {p: 0 for p in PARTITIONS}
    by_image = {i["image_id"]: group for group in groups for i in group["items"]}
    pins: dict[str, str] = {}

    def failure(code, message, proven=True, **details):
        violations.append({"code": code, "message": message, "proven_infeasible": proven, **details})

    def delta(part, size_delta, class_delta):
        error = sizes[part] * BPS - total * ratios[part]
        result = ((error + size_delta * BPS) ** 2 - error**2) * size_weight
        if stratified:
            for cls, change in class_delta.items():
                if not change:
                    continue
                error = counts[part][cls] * BPS - totals[cls] * ratios[part]
                result += ((error + change * BPS) ** 2 - error**2) * class_weights[cls]
        return result

    def negative(counter):
        return {cls: -n for cls, n in counter.items()}

    def place(group, part):
        old = assignments.get(group["id"])
        if old:
            sizes[old] -= group["size"]
            group_counts[old] -= 1
            counts[old].subtract(group["classes"])
        assignments[group["id"]] = part
        sizes[part] += group["size"]
        group_counts[part] += 1
        counts[part].update(group["classes"])

    def move_cost(group, destination):
        old = assignments[group["id"]]
        return delta(old, -group["size"], negative(group["classes"])) + delta(
            destination, group["size"], group["classes"]
        )

    def report(passes=0):
        complete = len(assignments) == len(groups)
        rows = [
            {
                "image_id": i["image_id"],
                "partition": assignments[group["id"]],
                "effective_group_key": group["key"],
            }
            for group in groups
            if group["id"] in assignments
            for i in group["items"]
        ]
        rows.sort(key=lambda item: item["image_id"])
        partitions = {}
        classes = {}
        for part in PARTITIONS:
            error = abs(sizes[part] * BPS - total * ratios[part])
            partitions[part] = {
                "requested_bps": ratios[part],
                "target_image_count": image_targets[part],
                "actual_image_count": sizes[part],
                "actual_group_count": group_counts[part],
                "target_group_count": targets(len(groups), ratios)[part],
                "actual_bps": float(Fraction(sizes[part] * BPS, total)),
                "absolute_error_bps": float(Fraction(error, total)),
            }
        for cls in sorted(set(source["class_ids"]) | set(totals)):
            count = totals[cls]
            classes[cls] = {
                "total_images": count,
                "partitions": {
                    p: {
                        "target_image_count": float(Fraction(count * ratios[p], BPS)),
                        "actual_image_count": counts[p][cls],
                        "absolute_error_bps": float(
                            Fraction(abs(counts[p][cls] * BPS - count * ratios[p]), count)
                        )
                        if count
                        else 0,
                    }
                    for p in PARTITIONS
                },
            }
        return {
            "preview_schema_version": "split-preview-1",
            "status": "FAILED" if violations else "PASSED",
            "assignment_complete": complete,
            "project_id": source["project_id"],
            "version_id": source["version_id"],
            "version_manifest_sha256": source["version_manifest_sha256"],
            "input_sha256": digest(canonical(source)),
            "config": config,
            "assignments": rows,
            "diagnostics": {
                "effective_groups": len(groups),
                "partitions": partitions,
                "classes": classes,
                "warnings": warnings,
                "violations": violations,
                "improvement_passes": passes,
                "decision_arithmetic": "exact rational",
                "note": "Algorithm preview only; not a released split or proof of a global optimum.",
            },
        }

    if source["enforce_group_split"] and not grouped:
        failure("GROUP_POLICY", "The source policy requires a group-aware strategy.")
    if not grouped and any(i["group_key"] is not None for i in items):
        warnings.append(
            {
                "code": "GROUPS_IGNORED",
                "message": "This strategy protects identical assets, but not group-key leakage.",
            }
        )
    missing = [i["image_id"] for i in items if i["group_key"] is None]
    if missing and (grouped or config["require_group_key"]):
        if config["require_group_key"] or config["missing_group_policy"] == "error":
            failure("MISSING_GROUP", "Images are missing required group keys.", image_ids=missing)
        else:
            warnings.append(
                {
                    "code": "MISSING_GROUP_SINGLETON",
                    "message": "Missing group keys use separate image components unless linked by identical assets.",
                    "image_ids": missing,
                }
            )
    if len(groups) < len(active):
        failure("TOO_FEW_GROUPS", "There are fewer effective groups than nonzero partitions.")
    for pin in config["pinned_assignments"]:
        group = by_image.get(pin["image_id"])
        part = pin["partition"]
        if group is None:
            failure("UNKNOWN_PIN", "Pinned image is not in the source version.", image_id=pin["image_id"])
        elif part not in active:
            failure("DISABLED_PARTITION_PIN", "Cannot pin an image into a zero-ratio partition.")
        elif group["id"] in pins and pins[group["id"]] != part:
            failure(
                "CONFLICTING_PINS",
                "An effective group is pinned to different partitions.",
                effective_group_key=group["key"],
            )
        else:
            pins[group["id"]] = part
    if config["strict_class_coverage"]:
        for cls in sorted(totals):
            support = sum(bool(g["classes"][cls]) for g in groups)
            if support < len(active):
                failure(
                    "RARE_CLASS",
                    "Class occurs in fewer effective groups than nonzero partitions.",
                    class_id=cls,
                    supporting_groups=support,
                )
    if violations:
        return report()
    for group in groups:
        if group["id"] in pins:
            place(group, pins[group["id"]])

    def tie(group):
        return digest(f"{config['seed']}|{config['algorithm_version']}|{group['id']}".encode())

    singleton_random = config["strategy"] == "random" and all(g["size"] == 1 for g in groups)
    remaining = [g for g in groups if g["id"] not in pins]
    if singleton_random:
        for group in sorted(remaining, key=lambda g: (tie(g), g["id"])):
            part = next(p for p in active if sizes[p] < image_targets[p])
            place(group, part)
    else:
        ordered = sorted(
            remaining,
            key=lambda g: (
                -sum((Fraction(n, totals[c]) for c, n in g["classes"].items()), Fraction()),
                -g["size"],
                tie(g),
                g["id"],
            ),
        )
        for group in ordered:
            part = min(active, key=lambda p: delta(p, group["size"], group["classes"]))
            place(group, part)
    # Repair empty partitions before optimizing; group atomicity and pins prevail.
    for part in active:
        if group_counts[part]:
            continue
        movable = [g for g in groups if g["id"] not in pins and group_counts[assignments[g["id"]]] > 1]
        if not movable:
            failure("PINNED_EMPTY_PARTITION", "Pins leave no movable group for a nonzero partition.")
            return report()
        chosen = min(movable, key=lambda g: (move_cost(g, part), g["id"]))
        place(chosen, part)

    passes = 0
    if not singleton_random:
        for _ in range(20):
            improved = False
            passes += 1
            for group in groups:
                if group["id"] in pins or group_counts[assignments[group["id"]]] <= 1:
                    continue
                for part in active:
                    if part != assignments[group["id"]] and move_cost(group, part) < 0:
                        place(group, part)
                        improved = True
                        if group_counts[part] <= 1:
                            break
            for index, first in enumerate(groups):
                if first["id"] in pins:
                    continue
                for second in groups[index + 1 :]:
                    p, q = assignments[first["id"]], assignments[second["id"]]
                    if p == q or second["id"] in pins:
                        continue
                    size_change = second["size"] - first["size"]
                    class_change = {
                        c: second["classes"][c] - first["classes"][c]
                        for c in first["classes"].keys() | second["classes"].keys()
                    }
                    if (
                        delta(p, size_change, class_change) + delta(q, -size_change, negative(class_change))
                        < 0
                    ):
                        place(first, q)
                        place(second, p)
                        improved = True
            if not improved:
                break
    for part in active:
        if abs(sizes[part] * BPS - total * ratios[part]) > config["size_tolerance_bps"] * total:
            failure(
                "SIZE_TOLERANCE",
                "No assignment within the size tolerance was found by this algorithm. Change the configuration explicitly.",
                False,
                partition=part,
            )
    for cls in sorted(totals):
        missing_parts = [p for p in active if not counts[p][cls]]
        if missing_parts:
            if config["strict_class_coverage"]:
                failure(
                    "CLASS_COVERAGE",
                    "This algorithm did not find full class coverage.",
                    False,
                    class_id=cls,
                    partitions=missing_parts,
                )
            else:
                warnings.append(
                    {
                        "code": "CLASS_COVERAGE",
                        "class_id": cls,
                        "partitions": missing_parts,
                        "message": "Class is absent from one or more nonzero partitions.",
                    }
                )
        for part in active:
            if (
                abs(counts[part][cls] * BPS - totals[cls] * ratios[part])
                > config["class_tolerance_bps"] * totals[cls]
            ):
                failure(
                    "CLASS_TOLERANCE",
                    "No assignment within the class tolerance was found by this algorithm.",
                    False,
                    class_id=cls,
                    partition=part,
                )
    return report(passes)


def compare_previews(before_source, before, after_source, after):
    """Compare complete diagnostic assignments; never publish a split from them."""
    from .domain import Problem

    if before_source["project_id"] != after_source["project_id"]:
        raise Problem("VALIDATION_FAILED", "Split comparison requires the same project.")

    def index(source, preview):
        if preview["input_sha256"] != digest(canonical(source)) or not preview["assignment_complete"]:
            raise Problem("VALIDATION_FAILED", "Preview does not bind to a complete source projection.")
        items = {i["image_id"]: i for i in source["items"]}
        rows = preview["assignments"]
        mapping = {a["image_id"]: a["partition"] for a in rows}
        if (
            set(mapping) != set(items)
            or len(rows) != len(items)
            or any(p not in PARTITIONS for p in mapping.values())
        ):
            raise Problem("VALIDATION_FAILED", "Preview assignments do not match the source images.")
        return items, mapping

    old_items, old = index(before_source, before)
    new_items, new = index(after_source, after)
    old_test_assets = {old_items[i]["asset_sha256"] for i in old if old[i] == "test"}
    old_test_groups = {
        old_items[i]["group_key"] for i in old if old[i] == "test" and old_items[i]["group_key"] is not None
    }
    leakage = [
        {
            "image_id": i,
            "same_asset": new_items[i]["asset_sha256"] in old_test_assets,
            "same_group": new_items[i]["group_key"] in old_test_groups,
        }
        for i in sorted(new)
        if new[i] == "train"
        and (new_items[i]["asset_sha256"] in old_test_assets or new_items[i]["group_key"] in old_test_groups)
    ]
    return {
        "added_images": sorted(new.keys() - old.keys()),
        "removed_images": sorted(old.keys() - new.keys()),
        "moved_images": [
            {"image_id": i, "from": old[i], "to": new[i]}
            for i in sorted(old.keys() & new.keys())
            if old[i] != new[i]
        ],
        "test_to_train_leakage": leakage,
        "warning": "Reusing a seed does not freeze a test set across versions. Use explicit pins and inspect asset/group changes.",
    }

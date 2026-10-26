"""Pure schema migration and semantic comparison for working checkpoints."""

from collections import Counter
from copy import deepcopy

from .domain import Problem, canonical, empty_content, uid, validate_content


def checkpoint_manifest(project_id, task_type, schema, records):
    return {
        "checkpoint_format": "working-checkpoint-1",
        "project_id": project_id,
        "task_type": task_type,
        "schema": schema,
        "records": records,
        "review_counts": dict(Counter(r["status"] for r in records)),
        "approved_release": False,
    }


def edited_schema(old, requested, project_id, number, reserved):
    previous = {e["class_id"]: e for e in old["entries"]}
    entries, seen, names = [], set(), set()
    next_index = max((e["export_index"] for e in reserved), default=-1) + 1
    for item in requested:
        ident, name = item.get("class_id"), item["display_name"].strip()
        if not name or name.casefold() in names or (ident and (ident not in previous or ident in seen)):
            raise Problem("INVALID_SCHEMA", "Use unique names and each existing class exactly once.")
        names.add(name.casefold())
        if ident:
            entry = dict(previous[ident])
            seen.add(ident)
        else:
            ident = uid()
            entry = {
                "class_id": ident,
                "stable_key": "class_" + ident.replace("-", ""),
                "export_index": next_index,
                "color_hex": "#4CC9A6",
            }
            next_index += 1
        entries.append(entry | {"display_name": name, "active": item["active"]})
    if seen != previous.keys():
        raise Problem(
            "INVALID_SCHEMA", "Retain existing class identities; deactivate instead of deleting rows."
        )
    if not any(e["active"] for e in entries):
        raise Problem("INVALID_SCHEMA", "Keep at least one active class.")
    return {"id": uid(), "project_id": project_id, "number": number, "entries": entries}


def migrate_content(content, mapping, entries, record, task):
    result = deepcopy(content)
    known = {e["class_id"] for e in entries}
    active = {e["class_id"] for e in entries if e["active"]}
    if not set(mapping) <= known or any(v is not None and v not in active for v in mapping.values()):
        raise Problem(
            "INVALID_MAPPING", "Use known source classes and active destinations; null removes a label."
        )
    result["shapes"] = [
        s | {"class_id": mapping.get(s["class_id"], s["class_id"])}
        for s in result["shapes"]
        if mapping.get(s["class_id"], s["class_id"]) is not None
    ]
    result["image_labels"] = [
        mapping.get(c, c) for c in result["image_labels"] if mapping.get(c, c) is not None
    ]
    used = {s["class_id"] for s in result["shapes"]} | set(result["image_labels"])
    if not used <= active:
        raise Problem(
            "CLASS_IN_USE", "Map or explicitly remove annotations of deactivated classes before applying."
        )
    return validate_content(result, record["width"], record["height"], task, active)


def content_of(document):
    return (
        {k: document[k] for k in ("shapes", "image_labels", "verified_empty")}
        if document
        else empty_content()
    )


def semantic_diff(before, after, before_content, after_content):
    old = {r["image_id"]: r for r in before["records"]}
    new = {r["image_id"]: r for r in after["records"]}
    changed, review_only, metadata = [], [], []
    for ident in sorted(old.keys() & new.keys()):
        if canonical(before_content[ident]) != canonical(after_content[ident]):
            changed.append(ident)
        elif (old[ident].get("review"), old[ident]["status"]) != (
            new[ident].get("review"),
            new[ident]["status"],
        ):
            review_only.append(ident)
        if any(
            old[ident].get(k) != new[ident].get(k) for k in ("group_key", "display_filename", "created_at")
        ):
            metadata.append(ident)

    def counts(contents):
        result: dict[str, int] = {}
        for content in contents.values():
            for ident in [s["class_id"] for s in content["shapes"]] + content["image_labels"]:
                result[ident] = result.get(ident, 0) + 1
        return result

    return {
        "added_images": sorted(new.keys() - old.keys()),
        "removed_images": sorted(old.keys() - new.keys()),
        "changed_annotations": changed,
        "review_only": review_only,
        "changed_image_metadata": metadata,
        "schema_changed": before["schema"]["sha256"] != after["schema"]["sha256"],
        "before_class_counts": counts(before_content),
        "after_class_counts": counts(after_content),
    }

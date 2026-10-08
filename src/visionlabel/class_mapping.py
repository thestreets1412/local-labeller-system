"""Explicit model mappings; restricted, data-only YOLO names reader (no YAML execution)."""

import ast
import json
import re

from .domain import Problem


def model_names(text):
    """Read JSON or the common YAML names block/list. Reject unsupported syntax."""

    def scalar(value):
        value = value.strip()
        if value.startswith("'"):
            match = re.fullmatch(r"'((?:[^']|'')*)'\s*(?:#.*)?", value)
            if not match:
                raise Problem("INVALID_MODEL_NAMES", "Invalid single-quoted class name.")
            return match[1].replace("''", "'")
        if value.startswith('"'):
            try:
                parsed, end = json.JSONDecoder().raw_decode(value)
                if value[end:].strip() and not value[end:].lstrip().startswith("#"):
                    raise ValueError
            except ValueError:
                raise Problem(
                    "INVALID_MODEL_NAMES", "Use plain or quoted class names without YAML tags."
                ) from None
            return parsed
        if any(c in value for c in "{}[]&*!|>"):
            raise Problem(
                "INVALID_MODEL_NAMES", "Unsupported YAML names syntax. Use one index: name per line."
            )
        return value.split(" #", 1)[0].strip()

    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise Problem("INVALID_MODEL_NAMES", "Duplicate model field or index.")
            result[key] = value
        return result

    try:
        document = json.loads(text, object_pairs_hook=unique_pairs)
        names = document["names"]
    except (ValueError, KeyError, TypeError):
        lines = text.splitlines()
        start = next((i for i, line in enumerate(lines) if re.match(r"^names\s*:", line)), None)
        if sum(bool(re.match(r"^names\s*:", line)) for line in lines) > 1:
            raise Problem("INVALID_MODEL_NAMES", "Duplicate names field.") from None
        if start is None:
            raise Problem("INVALID_MODEL_NAMES", "Model YAML must contain a top-level names field.") from None
        value = lines[start].split(":", 1)[1].strip()
        if value.startswith(("[", "{")):
            try:
                if "''" in value:
                    raise Problem(
                        "INVALID_MODEL_NAMES", "Use an indented names block for escaped single quotes."
                    )
                parsed = ast.parse(value, mode="eval").body
                if isinstance(parsed, ast.Dict):
                    if any(k is None for k in parsed.keys):
                        raise Problem("INVALID_MODEL_NAMES", "Dictionary expansion is not supported.")
                    unique_pairs([(ast.literal_eval(k), None) for k in parsed.keys if k is not None])
                names = ast.literal_eval(value)
            except (ValueError, SyntaxError):
                if value.startswith("[") and value.endswith("]"):
                    names = [scalar(v) for v in value[1:-1].split(",")]
                else:
                    raise Problem(
                        "INVALID_MODEL_NAMES", "Use a names list or indented index: name entries."
                    ) from None
        else:
            if value and not value.startswith("#"):
                raise Problem("INVALID_MODEL_NAMES", "Unsupported names field.") from None
            names = {}
            for line in lines[start + 1 :]:
                if not line.strip() or line.lstrip().startswith("#"):
                    continue
                if not line[0].isspace() and not line.startswith("- "):
                    break
                item = line.strip()
                if item.startswith("- "):
                    index, name = len(names), scalar(item[2:])
                else:
                    index_text, sep, value = item.partition(":")
                    if not sep or not index_text.isdecimal():
                        raise Problem(
                            "INVALID_MODEL_NAMES", "Expected an integer index and class name."
                        ) from None
                    index, name = int(index_text), scalar(value)
                if index in names:
                    raise Problem("INVALID_MODEL_NAMES", "Duplicate model class index.") from None
                names[index] = name
    if isinstance(names, list):
        names = dict(enumerate(names))
    if not isinstance(names, dict) or not names or len(names) > 1000:
        raise Problem("INVALID_MODEL_NAMES", "Model names must contain 1-1000 classes.")
    result = {}
    for index, name in names.items():
        if (
            not str(index).isascii()
            or not str(index).isdecimal()
            or not isinstance(name, str)
            or not name.strip()
        ):
            raise Problem("INVALID_MODEL_NAMES", "Invalid class index or name.")
        if int(index) in result:
            raise Problem("INVALID_MODEL_NAMES", "Duplicate model class index.")
        result[int(index)] = name.strip()
    if set(result) != set(range(len(result))) or len(set(result.values())) != len(result):
        raise Problem("INVALID_MODEL_NAMES", "Names must be unique with contiguous indices starting at zero.")
    return result


def parse_mapping(text, entries, *, complete=False):
    names = {e["display_name"]: e["class_id"] for e in entries}
    result = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        index, sep, name = line.partition("=")
        index, name = index.strip(), name.strip()
        if (
            not sep
            or not index.isascii()
            or not index.isdecimal()
            or int(index) in result
            or name not in names
        ):
            raise Problem("INVALID_MAPPING", "Use unique integer indices and exact project names: 0=part")
        result[int(index)] = names[name]
    if not result:
        raise Problem("INVALID_MAPPING", "Provide at least one class mapping.")
    if complete and (set(result) != set(range(len(entries))) or set(result.values()) != set(names.values())):
        raise Problem(
            "INVALID_MAPPING",
            "Export mapping must include each class exactly once with indices starting at zero.",
        )
    return result


def export_classes(classes, mapping):
    if mapping is None:
        return classes
    if (
        set(mapping) != {c["class_id"] for c in classes}
        or any(type(i) is not int for i in mapping.values())
        or set(mapping.values()) != set(range(len(classes)))
    ):
        raise Problem("INVALID_MAPPING", "Export mapping must be a complete permutation of project classes.")
    return [
        c | {"schema_export_index": c["export_index"], "export_index": mapping[c["class_id"]]}
        for c in classes
    ]

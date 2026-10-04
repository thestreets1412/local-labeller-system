"""Developer preview of frozen split projections; never writes canonical split state."""

import argparse
import json
import os
from pathlib import Path

from pydantic import ValidationError

from .domain import Problem, canonical, digest
from .split_contracts import normalized_config, normalized_input
from .splitting import compare_previews, plan_split


def read_json(path):
    if path.stat().st_size > 64 * 1024 * 1024:
        raise Problem("VALIDATION_FAILED", "Input exceeds the 64 MiB preview limit.")
    return json.loads(path.read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(
        description="Preview split algorithms against a frozen projection. Does not create a dataset version or production split."
    )
    parser.add_argument("--input", type=Path, required=True, help="Frozen split-projection-1 JSON")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--output", type=Path, required=True, help="New diagnostic JSON file (never overwritten)"
    )
    parser.add_argument("--compare-input", type=Path)
    parser.add_argument("--compare-preview", type=Path)
    args = parser.parse_args()
    if bool(args.compare_input) != bool(args.compare_preview):
        parser.error("Both --compare-input and --compare-preview are required for comparison.")
    try:
        source = normalized_input(read_json(args.input))
        config = normalized_config(read_json(args.config))
        result = plan_split(source, config)
        artifact = {
            "artifact_kind": "split-diagnostics-preview",
            "canonical_split": False,
            "provenance_verified": False,
            "report": result,
        }
        if args.compare_input:
            previous = read_json(args.compare_preview)
            artifact["comparison"] = compare_previews(
                normalized_input(read_json(args.compare_input)), previous["report"], source, result
            )
        data = canonical(artifact)
        with args.output.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        print(f"Preview {result['status']}. Not a production split. SHA-256: {digest(data)}")
        print(f"Diagnostics: {args.output.resolve()}")
        if result["status"] == "FAILED":
            parser.exit(
                2, "Constraints were not met. Inspect diagnostics and explicitly change the configuration.\n"
            )
    except ValidationError as exc:
        details = "; ".join(
            ".".join(map(str, e["loc"])) + ": " + e["msg"] for e in exc.errors(include_input=False)
        )
        parser.exit(1, "Invalid split input/config: " + details + "\n")
    except (Problem, OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(1, (exc.message if isinstance(exc, Problem) else str(exc)) + "\n")


if __name__ == "__main__":
    main()

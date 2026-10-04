"""Refresh Phase 3 API contracts while preserving previous phase snapshots."""

import json
import re
from pathlib import Path

from visionlabel.api import create_app

ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = (ROOT / "VisionLabel_DataTracking_Specification.md").read_text(encoding="utf-8")
    section = spec.split("### 10.2 JSON Schema Draft 2020-12", 1)[1].split("### 10.3", 1)[0]
    schema = json.loads(re.search(r"```json\s*(.*?)```", section, re.S).group(1))
    destination = ROOT / "src/visionlabel/schemas"
    destination.mkdir(exist_ok=True)
    (destination / "annotation-1.0.0.json").write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    output = ROOT / "docs/contracts"
    output.mkdir(parents=True, exist_ok=True)
    (output / "phase3-openapi.json").write_text(
        json.dumps(create_app(Path("unused")).openapi(), indent=2) + "\n", encoding="utf-8"
    )
    print("Annotation schema and Phase 3 OpenAPI refreshed; earlier snapshots retained.")


if __name__ == "__main__":
    main()

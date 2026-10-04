"""Collect installed notices and exact locked provenance. No runtime network calls."""

import hashlib
import json
import re
import tomllib
from importlib.metadata import distributions
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def main():
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))
    packages = {p["name"]: p for p in lock["package"]}
    runtime = set()

    def visit(name):
        if name in runtime:
            return
        runtime.add(name)
        for dependency in packages[name].get("dependencies", []):
            visit(dependency["name"])

    visit("visionlabel")
    destination = ROOT / "docs" / "license_inventory"
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    components = []
    errors = []
    allowed = {"MIT", "BSD-2-Clause", "BSD-3-Clause", "Apache-2.0", "Apache-2.0 OR BSD-2-Clause"}
    exceptions = {"certifi": "MPL-2.0", "typing-extensions": "PSF-2.0"}
    for dist in sorted(distributions(), key=lambda d: normalized(d.metadata["Name"])):
        name = normalized(dist.metadata["Name"])
        if name not in packages or name == "visionlabel":
            continue
        license_text = dist.metadata.get("License-Expression") or dist.metadata.get("License")
        if name == "colorama":
            license_text = "BSD-3-Clause"  # Verified from the installed LICENSE.txt.
        if license_text not in allowed and exceptions.get(name) != license_text:
            errors.append(name + ": " + str(license_text))
        notices = []
        native = []
        for file in dist.files or []:
            text = str(file)
            path = Path(dist.locate_file(file))
            if path.is_file() and (
                ".dist-info/" in text
                and any(token in path.name.lower() for token in ("license", "copying", "notice"))
            ):
                data = path.read_bytes()
                target = destination / "notices" / name / Path(*file.parts[1:])
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                notices.append(
                    {"path": target.relative_to(ROOT).as_posix(), "sha256": hashlib.sha256(data).hexdigest()}
                )
            if path.suffix.lower() in (".pyd", ".dll"):
                native.append({"path": text, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        if not notices:
            errors.append(name + ": missing installed notice")
        locked = packages[name]
        entry = {
            "name": name,
            "version": dist.version,
            "scope": "runtime" if name in runtime else "development",
            "license": license_text,
            "policy": "user-approved exception" if name in exceptions else "baseline",
            "notices": notices,
            "native_files": native,
            "source": locked.get("source"),
            "locked_artifacts": [{"url": a["url"], "hash": a["hash"]} for a in locked.get("wheels", [])],
        }
        entries.append(entry)
        components.append(
            {
                "type": "library",
                "name": name,
                "version": dist.version,
                "purl": f"pkg:pypi/{name}@{dist.version}",
                "licenses": [{"expression": license_text}],
                "properties": [{"name": "visionlabel:scope", "value": entry["scope"]}],
            }
        )
    report = {
        "python": "3.12.10",
        "platform": "Windows x64",
        "scope": "Installed Python distributions. See native-review.md for bundled native component evidence and remaining release checks.",
        "errors": errors,
        "packages": entries,
    }
    (destination / "inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (destination / "sbom.cdx.json").write_text(
        json.dumps(
            {"bomFormat": "CycloneDX", "specVersion": "1.6", "version": 1, "components": components}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )
    lines = [
        "# Third-party notices",
        "",
        "This development baseline retains the installed dependency license texts below.",
        "The user approved certifi/MPL-2.0, typing_extensions/PSF-2.0, and Dear PyGui's FreeType/FTL exception on 2026-10-03.",
        "NumPy/OpenCV are not installed in this Phase 1 environment.",
        "",
        "| Package | Version | Scope | License | Notices |",
        "|---|---|---|---|---|",
    ]
    for item in entries:
        links = ", ".join(f"[notice {i + 1}]({notice['path']})" for i, notice in enumerate(item["notices"]))
        lines.append(
            f"| {item['name']} | {item['version']} | {item['scope']} | {item['license']} | {links} |"
        )
    lines.extend(
        [
            "",
            "See [native component review](docs/license_inventory/native-review.md) for Dear PyGui and native-wheel evidence.",
            "Runtime uses Windows Imaging Component and the Windows-installed Tahoma font; these OS files are not copied or redistributed.",
            "Python/SQLite retain the runtime exceptions in the specification. Release packaging must include the Python runtime notices and an audit of the final installer contents.",
            "Build frontends/backends are provisioning tools, not bundled runtime; they require their own toolchain inventory before the Phase 6 installer release.",
        ]
    )
    (ROOT / "THIRD_PARTY_NOTICES.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"packages": len(entries), "errors": errors}))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

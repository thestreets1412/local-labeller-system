"""Provision an unsigned development wheel kit; not a Nuitka production release."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args):
    subprocess.run(args, cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.resolve()
    if destination.exists():
        parser.error("Output must be a new directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".visionlabel-kit-", dir=destination.parent) as temp:
        stage = Path(temp) / "kit"
        wheels = stage / "wheels"
        wheels.mkdir(parents=True)
        requirements = stage / "requirements.txt"
        run(
            [
                "uv",
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
                "--quiet",
            ]
        )
        run(
            [
                sys.executable,
                "-m",
                "pip",
                "download",
                "--only-binary=:all:",
                "--require-hashes",
                "-r",
                str(requirements),
                "--dest",
                str(wheels),
                "--quiet",
            ]
        )
        run(["uv", "build", "--wheel", "--out-dir", str(wheels)])
        app = next(wheels.glob("visionlabel-*.whl"))
        app_hash = hashlib.sha256(app.read_bytes()).hexdigest()
        with requirements.open("a", encoding="utf-8", newline="\n") as stream:
            stream.write(f"\nvisionlabel==0.1.0 --hash=sha256:{app_hash}\n")
        shutil.copyfile(ROOT / "scripts/offline_install.py", stage / "install.py")
        shutil.copyfile(ROOT / "scripts/Start-VisionLabel.ps1", stage / "Start-VisionLabel.ps1")
        shutil.copyfile(ROOT / "docs/operations-guide.md", stage / "OPERATIONS.md")
        shutil.copyfile(ROOT / "THIRD_PARTY_NOTICES.md", stage / "THIRD_PARTY_NOTICES.md")
        shutil.copytree(ROOT / "docs/license_inventory", stage / "license_inventory")
        files = []
        for path in sorted(stage.rglob("*")):
            if path.is_file():
                files.append(
                    {
                        "path": path.relative_to(stage).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        manifest = {
            "schema_version": 1,
            "profile": "local-development-wheel-kit",
            "production_qualified": False,
            "python": "3.12.10",
            "platform": "win-amd64",
            "lock_sha256": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
            "files": files,
        }
        (stage / "kit-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        run([sys.executable, str(stage / "install.py"), "--verify-only"])
        stage.rename(destination)
    print(f"Development kit ready: {destination}")


if __name__ == "__main__":
    main()

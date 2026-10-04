"""Build and install a wheel in a separate offline environment, then open the GUI."""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, cwd=ROOT):
    subprocess.run(command, cwd=cwd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    run(["uv", "build", "--wheel", "--out-dir", "dist"])
    artifact = ROOT / "dist/visionlabel-0.1.0-py3-none-any.whl"
    with tempfile.TemporaryDirectory(prefix="visionlabel-package-") as folder:
        work = Path(folder)
        requirements = work / "requirements.txt"
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
        wheelhouse = ROOT / "dist/wheelhouse"
        wheelhouse.mkdir(exist_ok=True)
        # Provision exact verified wheels before testing an offline installation.
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
                str(wheelhouse),
                "--quiet",
            ]
        )
        run(["uv", "venv", "--python", sys.executable, str(work / "venv"), "--quiet"])
        python = work / "venv/Scripts/python.exe"
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--offline",
                "--no-index",
                "--find-links",
                str(wheelhouse),
                "--require-hashes",
                "-r",
                str(requirements),
                "--quiet",
            ]
        )
        run(
            [
                "uv",
                "pip",
                "install",
                "--python",
                str(python),
                "--no-deps",
                "--offline",
                str(artifact),
                "--quiet",
            ]
        )
        # Run outside the repository to catch missing packaged modules/resources.
        run([str(python), "-m", "visionlabel.cli", "--help"], work)
        run(
            [
                str(python),
                "-c",
                "from pathlib import Path; from visionlabel.service import Service; s=Service(Path('data')); s.bootstrap('smoke','a-long-package-test-password'); s.close(); import visionlabel; print(visionlabel.__file__)",
            ],
            work,
        )
        run(
            [
                str(python),
                "-m",
                "visionlabel.split_preview",
                "--input",
                str(ROOT / "tests/fixtures/splitting/source.json"),
                "--config",
                str(ROOT / "tests/fixtures/splitting/config.json"),
                "--output",
                str(work / "split-preview.json"),
            ],
            work,
        )
        preview = json.loads((work / "split-preview.json").read_text(encoding="utf-8"))
        assert preview["report"]["status"] == "PASSED" and preview["canonical_split"] is False
        run(
            [
                str(python),
                "-m",
                "visionlabel.format_preview",
                "export-preview",
                "--input",
                str(ROOT / "tests/fixtures/formats/export-preview.json"),
                "--output",
                str(work / "format-preview.json"),
            ],
            work,
        )
        formats = json.loads((work / "format-preview.json").read_text(encoding="utf-8"))
        assert formats["canonical_export"] is False
        assert formats["files"][0]["label_text"] == "2 0.200000000 0.200000000 0.200000000 0.200000000\n"
        run(
            [
                str(python),
                "-m",
                "visionlabel.desktop",
                "--smoke-frames",
                "20",
                "--screenshot",
                str(args.output / "packaged-desktop.png"),
            ],
            work,
        )
        result = {
            "result": "passed",
            "artifact": artifact.name,
            "checks": [
                "wheel build",
                "offline runtime dependency install",
                "noneditable install outside repository",
                "packaged Alembic migration",
                "packaged desktop render",
                "packaged deterministic split preview CLI",
                "packaged YOLO format preview CLI",
            ],
            "scope": "Wheel smoke on development machine; not a Nuitka installer or clean-machine production qualification.",
        }
        (args.output / "package-smoke.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    main()

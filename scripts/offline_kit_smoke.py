"""Install a kit outside the checkout and exercise packaged operations and GUI."""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    kit, output = args.kit.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="visionlabel-offline-smoke-") as temp:
        root = Path(temp)
        target = root / "Installed app"

        def run(command):
            subprocess.run(command, cwd=root, check=True)

        run([sys.executable, str(kit / "install.py"), "--verify-only"])
        run([sys.executable, str(kit / "install.py"), "--target", str(target)])
        python = str(target / ".venv/Scripts/python.exe")
        run(
            [
                python,
                "-I",
                "-c",
                "from pathlib import Path; from visionlabel.service import Service; s=Service(Path('server')); s.bootstrap('admin','synthetic-drill-password'); s.close()",
            ]
        )
        run([python, "-I", "-m", "visionlabel.cli", "backup", "--root", "server", "--destination", "backup"])
        run([python, "-I", "-m", "visionlabel.cli", "verify-backup", "--backup-set", "backup"])
        run(
            [
                python,
                "-I",
                "-m",
                "visionlabel.cli",
                "restore",
                "--backup-set",
                "backup",
                "--destination",
                "restored",
            ]
        )
        run(
            [
                python,
                "-I",
                "-c",
                "from pathlib import Path; from visionlabel.service import Service; s=Service(Path('restored')); session=s.login('admin','synthetic-drill-password'); assert s.authenticate(session['token'])['username']=='admin'; s.close()",
            ]
        )
        run(
            [
                python,
                "-I",
                "-m",
                "visionlabel.desktop",
                "--smoke-frames",
                "20",
                "--screenshot",
                str(output / "offline-kit-desktop.png"),
            ]
        )
        result = {
            "result": "passed",
            "profile": "local-development-wheel-kit",
            "kit_manifest_sha256": hashlib.sha256((kit / "kit-manifest.json").read_bytes()).hexdigest(),
            "checks": [
                "kit hashes",
                "offline hash-required install in a new environment outside checkout",
                "packaged schema initialization",
                "packaged backup/verify/restore and login",
                "packaged desktop 20-frame render",
            ],
            "limitations": [
                "same development PC, not a clean machine",
                "not Nuitka or a production installer",
                "no blocked-egress firewall measurement",
                "no LAN/HTTPS acceptance",
                "packaged restore uses empty project database; full asset/annotation restore covered by integration tests",
            ],
        }
        (output / "offline-kit-smoke.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))


if __name__ == "__main__":
    main()

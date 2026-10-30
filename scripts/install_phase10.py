"""Install the committed Phase 10 wheels with bundled pip and pinned dependencies."""

import argparse
import hashlib
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APPLICATION = "visionlabel-0.1.5-py3-none-any.whl"
NATIVE = "visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl"


def run(command):
    subprocess.run([str(part) for part in command], check=True)


def verify_wheels(folder, names):
    expected = {}
    for line in (folder / "SHA256SUMS.txt").read_text(encoding="utf-8-sig").splitlines():
        checksum, name = line.split(maxsplit=1)
        expected[name.strip().lstrip("*")] = checksum.lower()
    for name in names:
        path = folder / name
        with path.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if actual != expected.get(name):
            raise ValueError("Wheel checksum mismatch: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", type=Path, default=ROOT / ".venv")
    parser.add_argument("--skip-native", action="store_true")
    parser.add_argument(
        "--wheelhouse", type=Path, help="Optional local runtime wheelhouse for offline installation"
    )
    args = parser.parse_args()
    if sys.platform != "win32" or sys.version_info[:3] != (3, 12, 10) or struct.calcsize("P") != 8:
        parser.error("Use Windows x64 with Python 3.12.10. No global packages will be installed.")
    folder = ROOT / "rush-wheel"
    names = [APPLICATION] + ([] if args.skip_native else [NATIVE])
    verify_wheels(folder, names)
    target = args.environment.absolute()
    python = target / "Scripts/python.exe"
    if target.exists():
        if not (target / "pyvenv.cfg").is_file() or not python.is_file():
            parser.error(
                "The destination exists but is not a Python virtual environment. Choose another path."
            )
    else:
        run([sys.executable, "-m", "venv", target])
    run(
        [
            python,
            "-I",
            "-c",
            "import sys,struct; assert sys.version_info[:3]==(3,12,10) and struct.calcsize('P')==8, 'Use Python 3.12.10 x64'",
        ]
    )
    print(
        "Close VisionLabel and DataTracking before upgrading. Back up existing server data first.", flush=True
    )
    source = ["--index-url", "https://pypi.org/simple"]
    if args.wheelhouse:
        source = ["--no-index", "--find-links", args.wheelhouse.resolve()]
    run(
        [
            python,
            "-I",
            "-m",
            "pip",
            "--isolated",
            "install",
            *source,
            "--only-binary=:all:",
            "--require-hashes",
            "-r",
            folder / "requirements-runtime.txt",
        ]
    )
    run(
        [
            python,
            "-I",
            "-m",
            "pip",
            "--isolated",
            "install",
            "--no-index",
            "--no-deps",
            "--force-reinstall",
            *(folder / name for name in names),
        ]
    )
    run([python, "-I", "-m", "pip", "check"])
    run(
        [
            python,
            "-I",
            "-c",
            "import visionlabel; from visionlabel import texture; print('VisionLabel:', visionlabel.__version__); print('Installed module:', visionlabel.__file__); print('Native display active:', texture._native_convert is not None)",
        ]
    )
    print(f'Installed. Start with: & "{python}" -I -m visionlabel.launcher', flush=True)
    print(
        "Dependencies came from PyPI (or the explicit offline wheelhouse); application/native wheels came from this checkout."
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print("Installation failed: " + str(exc), file=sys.stderr)
        sys.exit(1)

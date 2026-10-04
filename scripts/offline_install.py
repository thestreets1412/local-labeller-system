"""Install a verified local-development wheel kit using Python 3.12.10; no network."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(kit):
    manifest = json.loads((kit / "kit-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("profile") != "local-development-wheel-kit":
        raise ValueError("Unsupported kit manifest.")
    listed = set()
    for item in manifest["files"]:
        name = item["path"]
        if not isinstance(name, str) or any(c in name for c in ("\\", ":", "\x00")):
            raise ValueError("Invalid kit path.")
        parts = name.split("/")
        if (
            any(part in ("", ".", "..") for part in parts)
            or PurePosixPath(name).is_absolute()
            or name in listed
        ):
            raise ValueError("Duplicate or escaping kit path.")
        listed.add(name)
        path = kit.joinpath(*parts)
        walk = kit
        for part in parts:
            walk /= part
            if walk.is_symlink() or walk.is_junction():
                raise ValueError("Kit reparse points are not supported.")
        if not path.is_file() or not path.resolve().is_relative_to(kit.resolve()):
            raise ValueError("Kit file is missing or escapes its root.")
        if path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
            raise ValueError("Kit checksum mismatch: " + name)
    actual = {p.relative_to(kit).as_posix() for p in kit.rglob("*") if p.is_file()}
    if actual != listed | {"kit-manifest.json"}:
        raise ValueError("Kit has unexpected or unlisted files.")
    if not {"install.py", "requirements.txt", "Start-VisionLabel.ps1"} <= listed:
        raise ValueError("Kit is missing installation files.")
    return manifest


def install(kit, target):
    if sys.version_info[:3] != (3, 12, 10) or sys.platform != "win32":
        raise ValueError("Use Windows x64 with Python 3.12.10.")
    import struct

    if struct.calcsize("P") != 8:
        raise ValueError("Use 64-bit Python.")
    kit, target = kit.resolve(), target.absolute()
    for part in (target, *target.parents):
        if part.is_symlink() or part.is_junction():
            raise ValueError("Installation paths cannot use reparse points.")
    if target.exists() or target.resolve().is_relative_to(kit):
        raise ValueError("Choose a new installation folder outside this kit.")
    verify(kit)
    target.mkdir(parents=True)
    # An interrupted install retains its folder, but has no READY marker or launcher.
    # Operators can inspect/remove that explicit failed target and retry a new path.
    subprocess.run([sys.executable, "-I", "-m", "venv", str(target / ".venv")], check=True)
    python = target / ".venv/Scripts/python.exe"
    env = os.environ.copy()
    env["PIP_CONFIG_FILE"] = os.devnull
    subprocess.run(
        [
            str(python),
            "-I",
            "-m",
            "pip",
            "--isolated",
            "--disable-pip-version-check",
            "install",
            "--no-index",
            "--no-cache-dir",
            "--find-links",
            str(kit / "wheels"),
            "--require-hashes",
            "-r",
            str(kit / "requirements.txt"),
        ],
        env=env,
        check=True,
    )
    subprocess.run([str(python), "-I", "-m", "visionlabel.cli", "--help"], check=True)
    (target / "Start-VisionLabel.ps1").write_bytes((kit / "Start-VisionLabel.ps1").read_bytes())
    (target / "installed-kit.json").write_bytes((kit / "kit-manifest.json").read_bytes())
    print(f"Installed local development build in {target}. Use Start-VisionLabel.ps1.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    try:
        kit = Path(__file__).resolve().parent
        if args.verify_only:
            manifest = verify(kit)
            print(
                f"Verified {len(manifest['files'])} kit files. Checksums are integrity checks, not signatures."
            )
        elif args.target:
            install(kit, args.target)
        else:
            parser.error("--target or --verify-only is required.")
    except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f"Installation failed: {exc}\n")


if __name__ == "__main__":
    main()

import ctypes
import json
import os
import re
from pathlib import Path, PurePosixPath

from .domain import Problem, digest, uid


def local_directory(path: Path):
    path = path.absolute()
    if str(path).startswith("\\\\"):
        raise Problem("INVALID_STORAGE", "The database must be on a local fixed drive.")
    for parent in (path, *path.parents):
        if parent.is_symlink() or parent.is_junction():
            raise Problem("INVALID_STORAGE", "Database directories cannot use reparse points.")
    for variable in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        cloud = os.environ.get(variable)
        if cloud and path.resolve().is_relative_to(Path(cloud).resolve()):
            raise Problem("INVALID_STORAGE", "The database cannot be stored in a synced cloud directory.")
    if os.name == "nt":
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.anchor)) != 3:
            raise Problem("INVALID_STORAGE", "The database must be on a local fixed drive.")
        if ctypes.windll.kernel32.GetDriveTypeW(str(path.resolve().anchor)) != 3:
            raise Problem("INVALID_STORAGE", "Resolved storage must be on a local fixed drive.")
    return path.resolve()


def contained(root: Path, relative: str, exists=False):
    if "\\" in relative or ":" in relative or "\x00" in relative:
        raise Problem("INVALID_PATH", "Use a relative POSIX path inside the configured source.")
    parts = PurePosixPath(relative).parts
    if not parts or relative.startswith("/") or any(p in (".", "..") for p in relative.split("/")):
        raise Problem("INVALID_PATH", "Path escapes the configured source.")
    for part in parts:
        if part.endswith((" ", ".")) or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I):
            raise Problem("INVALID_PATH", "Reserved Windows path.")
    root = root.resolve()
    candidate = root.joinpath(*parts)
    if not candidate.resolve().is_relative_to(root):
        raise Problem("INVALID_PATH", "Path escapes the configured source.")
    walk = root
    for part in parts:
        walk /= part
        if walk.is_symlink() or walk.is_junction():
            raise Problem("INVALID_PATH", "Reparse points are not accepted.")
    if exists and not candidate.is_file():
        raise Problem("NOT_FOUND", "Source file not found.", 404)
    return candidate


class BlobStore:
    def __init__(self, root: Path):
        self.root = root
        root.mkdir(parents=True, exist_ok=True)

    def publish(self, relative, data):
        target = contained(self.root, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if digest(target.read_bytes()) != digest(data):
                raise Problem("CORRUPT_BLOB", "Immutable blob checksum mismatch.", 503)
            return
        temp = target.with_name(f".{uid()}.tmp")
        try:
            with temp.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                # MOVEFILE_WRITE_THROUGH; no REPLACE_EXISTING flag, so publication is immutable.
                kernel = ctypes.WinDLL("kernel32", use_last_error=True)
                kernel.MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_ulong]
                if not kernel.MoveFileExW(str(temp), str(target), 0x8):
                    error = ctypes.get_last_error()
                    if error in (80, 183):
                        raise FileExistsError(str(target))
                    raise ctypes.WinError(error)
            except FileExistsError:
                if target.read_bytes() != data:
                    raise Problem("CORRUPT_BLOB", "Immutable path collision.", 503) from None
        finally:
            temp.unlink(missing_ok=True)

    def read(self, path, sha):
        try:
            data = contained(self.root, path, exists=True).read_bytes()
        except (OSError, Problem) as exc:
            raise Problem("STORAGE_UNAVAILABLE", "Referenced content is unavailable.", 503) from exc
        if digest(data) != sha:
            raise Problem("CORRUPT_BLOB", "Referenced content failed checksum verification.", 503)
        return data

    def json(self, path, sha):
        return json.loads(self.read(path, sha))

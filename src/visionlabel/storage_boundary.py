"""Windows handle-pinned filesystem access for root-only storage management.

Every ancestor is held without FILE_SHARE_DELETE while a child is accessed.
OPEN_REPARSE_POINT inspects the entry itself, never a junction/symlink target.
Deletion uses the verified file handle, not a second path lookup.
"""

import ctypes as C
import hashlib
import msvcrt
import os
import re
from contextlib import ExitStack, contextmanager
from ctypes import wintypes as W
from pathlib import Path

from .domain import Problem


class FileInfo(C.Structure):
    _fields_ = [
        ("attributes", W.DWORD),
        ("creation", W.FILETIME),
        ("access", W.FILETIME),
        ("write", W.FILETIME),
        ("volume", W.DWORD),
        ("size_high", W.DWORD),
        ("size_low", W.DWORD),
        ("links", W.DWORD),
        ("index_high", W.DWORD),
        ("index_low", W.DWORD),
    ]


kernel = C.WinDLL("kernel32", use_last_error=True)
kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
kernel.CreateFileW.restype = W.HANDLE
kernel.CloseHandle.argtypes = [W.HANDLE]
kernel.GetFileInformationByHandle.argtypes = [W.HANDLE, C.POINTER(FileInfo)]
kernel.SetFileInformationByHandle.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD]


def info(handle):
    data = FileInfo()
    if not kernel.GetFileInformationByHandle(handle, C.byref(data)):
        raise C.WinError(C.get_last_error())
    return {
        "identity": f"{data.volume}:{data.index_high}:{data.index_low}",
        "bytes": (data.size_high << 32) | data.size_low,
        "mtime": (((data.write.dwHighDateTime << 32) | data.write.dwLowDateTime) // 10**7) - 11644473600,
        "write_ticks": (data.write.dwHighDateTime << 32) | data.write.dwLowDateTime,
        "blocked": bool(data.attributes & 0x400),
        "directory": bool(data.attributes & 0x10),
        "links": data.links,
    }


@contextmanager
def handle_at(path, access=0x80, disposition=3, share=3):
    handle = kernel.CreateFileW(str(path), access, share, None, disposition, 0x02200000, None)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    try:
        yield handle
    finally:
        kernel.CloseHandle(handle)


def denied(
    message="Path is outside the configured root or crosses a reparse point. Choose a root-contained path.",
):
    return Problem("STORAGE_BOUNDARY", message, 409)


class StorageBoundary:
    def __init__(self, root: Path):
        self.root = Path(os.path.abspath(root))
        if str(self.root).startswith("\\\\"):
            raise denied()
        self.identity = None
        with self.directory() as path:
            with handle_at(path) as handle:
                self.identity = info(handle)["identity"]

    def parts(self, relative):
        if not isinstance(relative, str) or not relative or any(c in relative for c in ("\\", ":", "\x00")):
            raise denied()
        parts = relative.split("/")
        for part in parts:
            if (
                part in ("", ".", "..")
                or part.endswith((" ", "."))
                or re.match(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", part, re.I)
            ):
                raise denied()
        return parts

    @contextmanager
    def directory(self, relative="", create=False):
        parts = self.parts(relative) if relative else []
        # Pin root ancestry too: a rename of root's parent must not redirect access.
        paths = list(reversed(self.root.parents)) + [self.root]
        paths += [self.root.joinpath(*parts[:i]) for i in range(1, len(parts) + 1)]
        with ExitStack() as stack:
            for path in paths:
                if create and path != self.root and path.is_relative_to(self.root):
                    try:
                        os.mkdir(path)
                    except FileExistsError:
                        pass
                handle = stack.enter_context(handle_at(path))
                data = info(handle)
                if data["blocked"] or not data["directory"]:
                    raise denied()
                if path == self.root and self.identity and data["identity"] != self.identity:
                    raise denied("Configured root changed. Reopen storage management and scan again.")
            yield self.root.joinpath(*parts)

    def mkdir(self, relative):
        with self.directory(relative, create=True):
            pass

    @contextmanager
    def entry(self, relative, *, access=0x80, disposition=3, share=3):
        parts = self.parts(relative)
        with self.directory("/".join(parts[:-1])) as parent:
            with handle_at(parent / parts[-1], access, disposition, share) as handle:
                yield handle

    def inventory_entry(self, relative):
        with self.entry(relative) as handle:
            return info(handle) | {"path": relative}

    @contextmanager
    def _stream(self, relative, create=False):
        with self.entry(
            relative, access=0xC0000000 if create else 0x80000000, disposition=1 if create else 3, share=1
        ) as handle:
            data = info(handle)
            if data["blocked"] or data["directory"] or (create and data["links"] != 1):
                raise denied()
            # Duplicate the handle: fd owns the duplicate, entry owns the original.
            duplicate = W.HANDLE()
            process = W.HANDLE(-1)
            kernel.DuplicateHandle.argtypes = [
                W.HANDLE,
                W.HANDLE,
                W.HANDLE,
                C.POINTER(W.HANDLE),
                W.DWORD,
                W.BOOL,
                W.DWORD,
            ]
            if not kernel.DuplicateHandle(process, handle, process, C.byref(duplicate), 0, False, 2):
                raise C.WinError(C.get_last_error())
            assert duplicate.value is not None
            fd = msvcrt.open_osfhandle(duplicate.value, os.O_BINARY | (os.O_RDWR if create else os.O_RDONLY))
            with os.fdopen(fd, "w+b" if create else "rb") as stream:
                yield stream
                if create:
                    stream.flush()
                    os.fsync(stream.fileno())

    def open_read(self, relative):
        return self._stream(relative)

    def open_new(self, relative):
        return self._stream(relative, True)

    def hash(self, relative):
        with self.open_read(relative) as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    def publish(self, source, destination, expected):
        """Rename the verified handle, never reopen a mutable source path."""
        parts = self.parts(destination)
        with self.directory("/".join(parts[:-1])) as parent:
            target = str(parent / parts[-1])
            encoded = target.encode("utf-16-le")

            class RenameInfo(C.Structure):
                _fields_ = [
                    ("replace", W.BOOL),
                    ("root", W.HANDLE),
                    ("length", W.DWORD),
                    ("name", C.c_byte * (len(encoded) + 2)),
                ]

            rename = RenameInfo()
            rename.length = len(encoded)
            C.memmove(C.addressof(rename) + RenameInfo.name.offset, encoded, len(encoded))
            with self.entry(source, access=0x10080, share=1) as handle:
                actual = info(handle)
                if (
                    actual["blocked"]
                    or actual["directory"]
                    or actual["links"] != 1
                    or any(actual[k] != expected[k] for k in ("identity", "bytes", "write_ticks"))
                ):
                    raise denied("Staged export changed. Prepare the export again.")
                if not kernel.SetFileInformationByHandle(handle, 3, C.byref(rename), C.sizeof(rename)):
                    raise C.WinError(C.get_last_error())

    def unlink_registered(self, relative, expected_identity):
        with self.entry(relative, access=0x10080, share=1) as handle:
            actual = info(handle)
            if actual["blocked"] or actual["directory"] or actual["links"] != 1:
                raise denied("Linked files cannot be removed by storage cleanup. Inspect the file manually.")
            if any(actual[k] != expected_identity[k] for k in ("identity", "bytes", "write_ticks")):
                raise denied("File changed since preview. Refresh the storage report and preview again.")
            delete = W.BOOL(True)
            if not kernel.SetFileInformationByHandle(handle, 4, C.byref(delete), C.sizeof(delete)):
                raise C.WinError(C.get_last_error())

    @contextmanager
    def database(self):
        """Pin DB directory and existing SQLite sidecars; never follow a redirected DB."""
        with self.directory("db") as folder, ExitStack() as stack:
            for suffix in ("", "-wal", "-shm", "-journal"):
                try:
                    handle = stack.enter_context(self.entry("db/data_tracking.sqlite3" + suffix))
                except FileNotFoundError:
                    if not suffix:
                        raise
                    continue
                data = info(handle)
                if data["blocked"] or data["directory"] or data["links"] != 1:
                    raise denied(
                        "Database or sidecar is linked. Restore a valid local database before scanning."
                    )
            yield folder

    def walk(self, relative=""):
        with self.directory(relative) as path:
            names = sorted(entry.name for entry in os.scandir(path))
            for name in names:
                child = f"{relative}/{name}" if relative else name
                try:
                    data = self.inventory_entry(child)
                    yield data
                    if data["directory"] and not data["blocked"]:
                        yield from self.walk(child)
                except (OSError, Problem) as exc:
                    yield {"path": child, "blocked": True, "error": str(exc), "bytes": 0, "directory": False}

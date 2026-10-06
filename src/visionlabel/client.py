"""HTTP-only client and private local cache/recovery files."""

import ctypes as C
import json
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .domain import Problem, canonical, digest, uid


class Client:
    def __init__(self, url="http://127.0.0.1:8765"):
        parsed = urlsplit(url)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in ("localhost", "127.0.0.1")
            or parsed.username
            or parsed.password
        ):
            raise Problem("INVALID_SERVER", "Phase 1 supports HTTP on loopback only.")
        self.url = url.rstrip("/")
        self.http = httpx.Client(
            base_url=self.url + "/api/v1", timeout=30, trust_env=False, follow_redirects=False
        )
        self.user = None
        self.instance = uid()

    def close(self):
        self.http.close()

    def request(self, method, path, body=None, claim=None, key=None, raw=False):
        headers = {}
        if key:
            headers["Idempotency-Key"] = key
        if claim:
            headers.update(
                {
                    "X-Claim-ID": claim["claim_id"],
                    "X-Claim-Token": claim["claim_token"],
                    "X-Claim-Generation": str(claim["generation"]),
                }
            )
        try:
            response = self.http.request(method, path, json=body, headers=headers)
        except httpx.HTTPError as exc:
            raise Problem(
                "DISCONNECTED", "Cannot reach the server. Your local draft is preserved.", 503
            ) from exc
        if response.is_error:
            try:
                error = response.json()["error"]
            except (ValueError, KeyError):
                error = {
                    "code": "SERVER_ERROR",
                    "message": "The server could not complete the request.",
                    "details": {},
                }
            raise Problem(error["code"], error["message"], response.status_code, **error.get("details", {}))
        if response.status_code == 204:
            return None
        return response.content if raw else response.json()

    def login(self, username, password):
        result = self.request("POST", "/auth/login", {"username": username, "password": password})
        self.http.headers["Authorization"] = "Bearer " + result["token"]
        self.user = result["user"]
        return self.user

    def download_export(self, job_id, destination, result):
        from .working_export import install_archive

        destination = Path(destination).absolute()
        if destination.exists() or not destination.parent.is_dir():
            raise Problem("INVALID_DESTINATION", "Choose a new folder inside an existing parent folder.")
        with tempfile.TemporaryDirectory(prefix=".visionlabel-download-", dir=destination.parent) as folder:
            archive = Path(folder) / "dataset.zip"
            try:
                with self.http.stream("GET", f"/working-exports/{job_id}/download", timeout=120) as response:
                    if response.is_error:
                        response.read()
                        error = response.json().get("error", {})
                        raise Problem(
                            error.get("code", "DOWNLOAD_FAILED"),
                            error.get("message", "Export download failed."),
                            response.status_code,
                        )
                    size = 0
                    with archive.open("xb") as stream:
                        for chunk in response.iter_bytes(1024 * 1024):
                            size += len(chunk)
                            if size > result["bytes"]:
                                raise Problem("CORRUPT_EXPORT", "Archive exceeds its expected size.")
                            stream.write(chunk)
                        stream.flush()
                        os.fsync(stream.fileno())
                if size != result["bytes"]:
                    raise Problem("CORRUPT_EXPORT", "Archive download was incomplete.")
                return install_archive(archive, destination, result["sha256"])
            except httpx.HTTPError as exc:
                raise Problem(
                    "DISCONNECTED", "Export download interrupted. Retry saving the prepared dataset.", 503
                ) from exc

    def list_all(self, path):
        result = []
        cursor = None
        while True:
            separator = "&" if "?" in path else "?"
            page = self.request(
                "GET", path + separator + "limit=500" + ("&cursor=" + cursor if cursor else "")
            )
            result.extend(page["items"])
            cursor = page["next_cursor"]
            if not cursor:
                return result


class DataBlob(C.Structure):
    _fields_ = [("size", C.c_ulong), ("data", C.POINTER(C.c_ubyte))]


def protect(data: bytes, decrypt=False):
    """DPAPI, bound to the signed-in Windows user. Tokens are never persisted."""
    array = (C.c_ubyte * len(data)).from_buffer_copy(data)
    source, output = DataBlob(len(data), array), DataBlob()
    crypt = C.WinDLL("crypt32", use_last_error=True)
    function = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    if not function(C.byref(source), None, None, None, None, 1, C.byref(output)):
        raise OSError(C.get_last_error(), "Windows could not protect the local recovery draft.")
    try:
        return C.string_at(output.data, output.size)
    finally:
        kernel = C.WinDLL("kernel32")
        kernel.LocalFree.argtypes = [C.c_void_p]
        kernel.LocalFree(C.cast(output.data, C.c_void_p))


class LocalStore:
    def __init__(self, server, user_id, root=None):
        base = Path(root or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "VisionLabel")
        self.scope = digest(f"{server}/{user_id}".encode())[:24]
        self.root = base / self.scope
        self.root.mkdir(parents=True, exist_ok=True)
        self.prune_cache()

    def draft_path(self, image_id):
        return self.root / f"{image_id}.draft"

    def save_draft(self, image_id, body):
        path = self.draft_path(image_id)
        temp = path.with_suffix(".tmp")
        with temp.open("wb") as stream:
            stream.write(protect(canonical(body)))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)

    def load_draft(self, image_id):
        path = self.draft_path(image_id)
        return json.loads(protect(path.read_bytes(), True)) if path.exists() else None

    def remove_draft(self, image_id):
        self.draft_path(image_id).unlink(missing_ok=True)

    def archive_draft(self, image_id):
        path = self.draft_path(image_id)
        if path.exists():
            path.rename(self.root / f"{image_id}-{uid()}.archived-draft")

    def prune_cache(self):
        files = sorted(self.root.glob("*.cache"), key=lambda p: p.stat().st_mtime, reverse=True)
        size = 0
        for path in files:
            info = path.stat()
            size += info.st_size
            if size > 1024 * 1024 * 1024 or info.st_mtime < time.time() - 30 * 86400:
                path.unlink(missing_ok=True)

    def cached_image(self, image, data):
        if digest(data) != image["asset_sha256"]:
            raise Problem("CORRUPT_IMAGE", "Downloaded image failed checksum verification.", 503)
        # Temporary decoded input only; the image cache itself is DPAPI encrypted.
        path = self.root / f"{image['asset_sha256']}.cache"
        if not path.exists():
            temp = path.with_suffix(".tmp")
            temp.write_bytes(protect(data))
            os.replace(temp, path)
            self.prune_cache()
        return data

    def read_cached(self, image):
        path = self.root / f"{image['asset_sha256']}.cache"
        if not path.exists():
            return None
        try:
            data = protect(path.read_bytes(), True)
            if digest(data) == image["asset_sha256"]:
                return data
        except (OSError, ValueError):
            pass
        path.unlink(missing_ok=True)
        return None

    def decode_image(self, image, data):
        from .imaging import decode

        fd, path = tempfile.mkstemp(suffix="." + image["extension"], dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
            return decode(Path(path), max_edge=2048)
        finally:
            Path(path).unlink(missing_ok=True)

    def clear_cache(self):
        for path in self.root.glob("*.cache"):
            path.unlink(missing_ok=True)

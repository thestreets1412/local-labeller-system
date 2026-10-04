"""Windows' WIC codec: original raster, no EXIF transform, no bundled codec."""

import ctypes as C
import json
import os
import struct
import subprocess
import sys
import zlib
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from uuid import UUID

from .domain import Problem


def image_header(data):
    if len(data) > 50 * 1024 * 1024:
        raise Problem("INVALID_IMAGE", "Image exceeds 50 MiB.")
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        if len(data) < 33 or data[12:16] != b"IHDR":
            raise Problem("INVALID_IMAGE", "Invalid PNG header.")
        width, height = struct.unpack(">II", data[16:24])
        pos = 8
        while pos + 12 <= len(data):
            size = int.from_bytes(data[pos : pos + 4], "big")
            if pos + size + 12 > len(data):
                raise Problem("INVALID_IMAGE", "Truncated PNG chunk.")
            expected = int.from_bytes(data[pos + size + 8 : pos + size + 12], "big")
            if zlib.crc32(data[pos + 4 : pos + size + 8]) & 0xFFFFFFFF != expected:
                raise Problem("INVALID_IMAGE", "PNG checksum failed.")
            if data[pos + 4 : pos + 8] == b"acTL":
                raise Problem("INVALID_IMAGE", "Animated images are not supported.")
            pos += size + 12
        extension = "png"
    elif data[:2] == b"\xff\xd8":
        width = height = 0
        pos = 2
        while pos + 4 <= len(data):
            if data[pos] != 255:
                break
            while pos < len(data) and data[pos] == 255:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in (0xDA, 0xD9):
                break
            size = int.from_bytes(data[pos : pos + 2], "big")
            if size < 2 or pos + size > len(data):
                break
            if marker in (0xC0, 0xC1, 0xC2) and size >= 8:
                height, width = struct.unpack(">HH", data[pos + 3 : pos + 7])
                break
            pos += size
        extension = "jpg"
    else:
        raise Problem("INVALID_IMAGE", "Only JPEG and PNG are supported.")
    if not width or not height or width * height > 40_000_000:
        raise Problem("INVALID_IMAGE", "Invalid dimensions or image exceeds 40 megapixels.")
    return width, height, extension


def decode(path: Path, max_edge=0):
    if os.name != "nt":
        raise RuntimeError("WIC requires Windows.")
    data = path.read_bytes()
    width, height, ext = image_header(data)
    dll = C.OleDLL("ole32")
    refs = []

    def guid(text):
        return (C.c_ubyte * 16).from_buffer_copy(UUID(text).bytes_le)

    def call(obj, slot, types, *args):
        vtable = C.cast(obj, C.POINTER(C.POINTER(C.c_void_p))).contents
        fn = C.WINFUNCTYPE(C.c_long, C.c_void_p, *types)(vtable[slot])
        result = fn(obj, *args)
        if result < 0:
            raise Problem("INVALID_IMAGE", "Windows could not decode this image.")

    dll.CoInitializeEx(None, 0)
    try:
        factory = C.c_void_p()
        result = dll.CoCreateInstance(
            C.byref(guid("cacaf262-9370-4615-a13b-9f5539da4c0a")),
            None,
            1,
            C.byref(guid("ec5ec8a9-c395-4314-9c77-54d7a935ff70")),
            C.byref(factory),
        )
        if result < 0:
            raise RuntimeError("Windows Imaging Component is unavailable.")
        refs.append(factory)
        decoder = C.c_void_p()
        call(
            factory,
            3,
            [C.c_wchar_p, C.c_void_p, C.c_ulong, C.c_ulong, C.c_void_p],
            str(path),
            None,
            0x80000000,
            0,
            C.byref(decoder),
        )
        refs.append(decoder)
        count = C.c_uint()
        call(decoder, 12, [C.c_void_p], C.byref(count))
        if count.value != 1:
            raise Problem("INVALID_IMAGE", "Multi-frame images are not supported.")
        frame = C.c_void_p()
        call(decoder, 13, [C.c_uint, C.c_void_p], 0, C.byref(frame))
        refs.append(frame)
        w, h = C.c_uint(), C.c_uint()
        call(frame, 3, [C.c_void_p, C.c_void_p], C.byref(w), C.byref(h))
        if (w.value, h.value) != (width, height):
            raise Problem("INVALID_IMAGE", "Image dimensions are inconsistent.")
        source = frame
        if max_edge and max(width, height) > max_edge:
            factor = max_edge / max(width, height)
            width, height = max(1, round(width * factor)), max(1, round(height * factor))
            scaler = C.c_void_p()
            call(factory, 11, [C.c_void_p], C.byref(scaler))
            refs.append(scaler)
            call(scaler, 8, [C.c_void_p, C.c_uint, C.c_uint, C.c_int], frame, width, height, 3)
            source = scaler
        converter = C.c_void_p()
        call(factory, 10, [C.c_void_p], C.byref(converter))
        refs.append(converter)
        call(
            converter,
            8,
            [C.c_void_p, C.c_void_p, C.c_int, C.c_void_p, C.c_double, C.c_int],
            source,
            C.byref(guid("f5c7ad2d-6a8d-43dd-a7a8-a29935261ae9")),
            0,
            None,
            0.0,
            0,
        )
        pixels = (C.c_ubyte * (width * height * 4))()
        call(converter, 7, [C.c_void_p, C.c_uint, C.c_uint, C.c_void_p], None, width * 4, len(pixels), pixels)
        return width, height, bytes(pixels), ext
    finally:
        for ref in reversed(refs):
            vtable = C.cast(ref, C.POINTER(C.POINTER(C.c_void_p))).contents
            C.WINFUNCTYPE(C.c_ulong, C.c_void_p)(vtable[2])(ref)
        dll.CoUninitialize()


def exif_orientation(data):
    """Read the TIFF orientation tag only; never transform original pixels."""
    start = data.find(b"Exif\x00\x00")
    if start < 0:
        return 1
    tiff = data[start + 6 :]
    try:
        order = "<" if tiff[:2] == b"II" else ">" if tiff[:2] == b"MM" else None
        if not order or struct.unpack_from(order + "H", tiff, 2)[0] != 42:
            return 1
        offset = struct.unpack_from(order + "I", tiff, 4)[0]
        count = struct.unpack_from(order + "H", tiff, offset)[0]
        for index in range(min(count, 4096)):
            pos = offset + 2 + 12 * index
            tag, kind, length = struct.unpack_from(order + "HHI", tiff, pos)
            if tag == 274 and kind == 3 and length == 1:
                return struct.unpack_from(order + "H", tiff, pos + 8)[0]
    except (struct.error, IndexError):
        pass
    return 1


def inspect_image(path: Path):
    """Decode in a disposable process so a malformed codec input cannot kill the service."""
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
    try:
        result = subprocess.run(
            [getattr(sys, "_base_executable", sys.executable), "-m", "visionlabel.imaging", str(path)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired as exc:
        raise Problem("INVALID_IMAGE", "Image decode exceeded its time limit.") from exc
    if result.returncode != 0:
        raise Problem("INVALID_IMAGE", "Image decode failed or exceeded its memory limit.")
    result_json = json.loads(result.stdout)
    return result_json["width"], result_json["height"]


class DecoderSession:
    """One bounded, isolated decoder reused within a single import job."""

    def __init__(self):
        self._start()

    def _start(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent)
        self.process = subprocess.Popen(
            [getattr(sys, "_base_executable", sys.executable), "-m", "visionlabel.imaging", "--worker"],
            env=env,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.reader = ThreadPoolExecutor(max_workers=1)

    def inspect(self, path):
        if self.process.poll() is not None:
            self.close()
            self._start()
        assert self.process.stdin is not None and self.process.stdout is not None
        try:
            self.process.stdin.write(json.dumps(str(path)) + "\n")
            self.process.stdin.flush()
            response = self.reader.submit(self.process.stdout.readline).result(timeout=20)
            result = json.loads(response)
            if "error" in result:
                raise Problem("INVALID_IMAGE", result["error"])
            return result["width"], result["height"]
        except (TimeoutError, BrokenPipeError, ValueError) as exc:
            self.process.kill()
            self.process.wait(timeout=5)
            raise Problem("INVALID_IMAGE", "Decoder failed or exceeded its resource limits.") from exc

    def close(self):
        assert self.process.stdin is not None and self.process.stdout is not None
        try:
            self.process.stdin.close()
        except BrokenPipeError:
            pass
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)
        self.reader.shutdown(wait=True)
        self.process.stdout.close()


def limit_worker_memory():
    class Basic(C.Structure):
        _fields_ = [
            ("process_time", C.c_longlong),
            ("job_time", C.c_longlong),
            ("flags", C.c_ulong),
            ("min_working", C.c_size_t),
            ("max_working", C.c_size_t),
            ("processes", C.c_ulong),
            ("affinity", C.c_size_t),
            ("priority", C.c_ulong),
            ("scheduling", C.c_ulong),
        ]

    class Extended(C.Structure):
        _fields_ = [
            ("basic", Basic),
            ("io", C.c_ulonglong * 6),
            ("memory", C.c_size_t),
            ("job_memory", C.c_size_t),
            ("peak_process", C.c_size_t),
            ("peak_job", C.c_size_t),
        ]

    kernel = C.WinDLL("kernel32", use_last_error=True)
    kernel.CreateJobObjectW.restype = C.c_void_p
    kernel.GetCurrentProcess.restype = C.c_void_p
    kernel.SetInformationJobObject.argtypes = [C.c_void_p, C.c_int, C.c_void_p, C.c_ulong]
    kernel.AssignProcessToJobObject.argtypes = [C.c_void_p, C.c_void_p]
    handle = kernel.CreateJobObjectW(None, None)
    limits = Extended()
    limits.basic.flags = 0x100  # JOB_OBJECT_LIMIT_PROCESS_MEMORY
    limits.memory = 768 * 1024 * 1024
    if (
        not handle
        or not kernel.SetInformationJobObject(handle, 9, C.byref(limits), C.sizeof(limits))
        or not kernel.AssignProcessToJobObject(handle, kernel.GetCurrentProcess())
    ):
        raise OSError(C.get_last_error(), "Could not establish decoder resource limits.")
    return handle  # The kernel closes it when this disposable process exits.


if __name__ == "__main__":
    handle = limit_worker_memory()
    if sys.argv[1] == "--worker":
        for line in sys.stdin:
            try:
                width, height, _, _ = decode(Path(json.loads(line)))
                result = {"width": width, "height": height}
            except (Problem, OSError) as exc:
                result = {"error": exc.message if isinstance(exc, Problem) else "Image could not be decoded."}
            print(json.dumps(result), flush=True)
    else:
        width, height, _, _ = decode(Path(sys.argv[1]))
        print(json.dumps({"width": width, "height": height}))

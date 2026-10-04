"""Generate nonconfidential PNGs using only the standard library."""

import struct
import zlib
from pathlib import Path


def png_bytes(index=0, width=640, height=400):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    pixels = bytearray()
    for y in range(height):
        pixels.append(0)
        for x in range(width):
            if x == 0 and y == 0:
                pixels.extend((index & 255, (index >> 8) & 255, (index >> 16) & 255))
            elif 70 + index % 40 < x < 230 + index % 40 and 70 < y < 240:
                pixels.extend((72, 198, 158))
            elif 340 < x < 520 and 130 + index % 30 < y < 300 + index % 30:
                pixels.extend((245, 169, 79))
            else:
                pixels.extend((24 + (index % 30), 30 + (x // 32) % 12, 40 + (y // 32) % 12))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(pixels)))
        + chunk(b"IEND", b"")
    )


def create_samples(folder: Path, count=100):
    folder.mkdir(parents=True, exist_ok=True)
    for index in range(count):
        path = folder / f"sample_{index + 1:04d}.png"
        if not path.exists():
            path.write_bytes(png_bytes(index))

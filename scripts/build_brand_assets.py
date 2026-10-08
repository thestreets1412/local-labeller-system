"""Rebuild original VisionLabel vector/PNG/Windows ICO assets using only stdlib."""

import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "src/visionlabel/assets"
NAVY = (19, 23, 30, 255)
MINT = (76, 201, 166, 255)
WHITE = (238, 247, 244, 255)
SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <title>VisionLabel</title>
  <desc>A V inside a mint annotation rectangle with four resize handles.</desc>
  <rect width="100" height="100" rx="22" fill="#13171e"/>
  <rect x="24" y="24" width="52" height="52" fill="none" stroke="#4cc9a6" stroke-width="4"/>
  <path d="M34 47 L46 62 L66 38" fill="none" stroke="#eef7f4" stroke-width="7"
        stroke-linecap="round" stroke-linejoin="round"/>
  <g fill="#4cc9a6">
    <rect x="19" y="19" width="10" height="10"/>
    <rect x="71" y="19" width="10" height="10"/>
    <rect x="19" y="71" width="10" height="10"/>
    <rect x="71" y="71" width="10" height="10"/>
  </g>
</svg>
'''


def distance(x, y, ax, ay, bx, by):
    t = max(0, min(1, ((x - ax) * (bx - ax) + (y - ay) * (by - ay)) / (
        (bx - ax) ** 2 + (by - ay) ** 2
    )))
    return math.hypot(x - ax - t * (bx - ax), y - ay - t * (by - ay))


def color(x, y):
    if math.hypot(max(22 - x, 0, x - 78), max(22 - y, 0, y - 78)) > 22:
        return (0, 0, 0, 0)
    if ((19 <= x <= 29 or 71 <= x <= 81) and (19 <= y <= 29 or 71 <= y <= 81)):
        return MINT
    if 22 <= x <= 78 and 22 <= y <= 78 and not (26 < x < 74 and 26 < y < 74):
        return MINT
    if min(distance(x, y, 34, 47, 46, 62), distance(x, y, 46, 62, 66, 38)) <= 3.5:
        return WHITE
    return NAVY


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def png(size):
    samples = 4 if size <= 256 else 2
    raw = bytearray()
    for row in range(size):
        raw.append(0)
        for col in range(size):
            pixels = [color((col + (sx + .5) / samples) * 100 / size,
                            (row + (sy + .5) / samples) * 100 / size)
                      for sy in range(samples) for sx in range(samples)]
            # Average in premultiplied alpha to avoid dark fringes on light backgrounds.
            alpha = sum(p[3] for p in pixels)
            raw.extend(round(sum(p[c] * p[3] for p in pixels) / alpha) if alpha else 0
                       for c in range(3))
            raw.append(round(alpha / len(pixels)))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    OUT.mkdir(exist_ok=True)
    (OUT / "visionlabel.svg").write_text(SVG, encoding="utf-8", newline="\n")
    sizes = (16, 20, 24, 32, 40, 48, 64, 128, 256)
    images = [(size, png(size)) for size in sizes]
    offset = 6 + 16 * len(images)
    entries = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    for size, data in images:
        entries.extend(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    (OUT / "visionlabel.ico").write_bytes(entries + b"".join(data for _, data in images))
    (OUT / "visionlabel-64.png").write_bytes(dict(images)[64])
    (OUT / "visionlabel-1024.png").write_bytes(png(1024))


if __name__ == "__main__":
    main()

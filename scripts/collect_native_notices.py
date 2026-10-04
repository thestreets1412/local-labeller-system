"""Provisioning-only download of pinned upstream license texts; never executed by the app."""

import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://raw.githubusercontent.com/hoffstadt/DearPyGui/v2.3.1/"
SOURCES = {
    "imgui-MIT.txt": "https://raw.githubusercontent.com/ocornut/imgui/3912b3d9a9c1b3f17431aebafd86d2f40ee6e59c/LICENSE.txt",
    "implot-MIT.txt": "https://raw.githubusercontent.com/epezent/implot/4707b245fbcd69075b1a8a74fa8d2435561b3134/LICENSE",
    "imnodes-MIT.txt": BASE + "thirdparty/imnodes/LICENSE.md",
    "ImGuiFileDialog-MIT.txt": BASE + "thirdparty/ImGuiFileDialog/LICENSE",
    "FreeType-FTL.txt": "https://raw.githubusercontent.com/freetype/freetype/8cf046c38d4c6ada76ba070562beff0d5041f795/docs/FTL.TXT",
    "FreeType-LICENSE.txt": "https://raw.githubusercontent.com/freetype/freetype/8cf046c38d4c6ada76ba070562beff0d5041f795/docs/LICENSE.TXT",
    "stb_image-MIT.txt": BASE + "thirdparty/stb/stb_image.h",
    "stb_image_write-MIT.txt": BASE + "thirdparty/stb/stb_image_write.h",
}


def main():
    destination = ROOT / "docs/license_inventory/native-notices"
    destination.mkdir(parents=True, exist_ok=True)
    entries = []
    for filename, url in SOURCES.items():
        with urllib.request.urlopen(url, timeout=30) as response:
            original = response.read()
        text = original.decode("utf-8")
        if filename.startswith("stb_"):
            start = text.rfind("ALTERNATIVE A")
            end = text.find("ALTERNATIVE B", start)
            if start < 0 or end < 0:
                raise ValueError("MIT license marker changed; inspect upstream before proceeding.")
            text = text[start:end]
        data = text.encode("utf-8")
        (destination / filename).write_bytes(data)
        entries.append(
            {
                "file": filename,
                "source": url,
                "source_sha256": hashlib.sha256(original).hexdigest(),
                "notice_sha256": hashlib.sha256(data).hexdigest(),
            }
        )
    (destination / "sources.json").write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    print(f"Retained {len(entries)} pinned native notices.")


if __name__ == "__main__":
    main()

import hashlib
import json
import runpy
from pathlib import Path

import pytest

VERIFY = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/offline_install.py"))["verify"]


def fixture_kit(path):
    files = []
    for name in ("install.py", "requirements.txt", "Start-VisionLabel.ps1", "wheels/example.whl"):
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = b"fixture bytes"
        target.write_bytes(data)
        files.append({"path": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schema_version": 1, "profile": "local-development-wheel-kit", "files": files}
    (path / "kit-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return manifest


def test_kit_verified_and_tamper_rejected(tmp_path):
    manifest = fixture_kit(tmp_path)
    assert VERIFY(tmp_path) == manifest
    (tmp_path / "wheels/example.whl").write_bytes(b"altered wheel")
    with pytest.raises(ValueError, match="checksum"):
        VERIFY(tmp_path)


@pytest.mark.parametrize(
    "name", ["../outside", "D:/outside", "/outside", "wheels\\outside", "wheels//outside", "./outside"]
)
def test_kit_paths_cannot_escape(tmp_path, name):
    manifest = fixture_kit(tmp_path)
    manifest["files"][0]["path"] = name
    (tmp_path / "kit-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError):
        VERIFY(tmp_path)


def test_kit_rejects_unlisted_files(tmp_path):
    fixture_kit(tmp_path)
    (tmp_path / "unexpected.whl").write_bytes(b"extra")
    with pytest.raises(ValueError, match="unlisted"):
        VERIFY(tmp_path)

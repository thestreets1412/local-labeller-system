import os
import subprocess

import pytest

from visionlabel.domain import Problem


def boundary(root):
    from visionlabel.storage_boundary import StorageBoundary

    return StorageBoundary(root)


def test_sibling_prefix_is_not_contained(tmp_path):
    root = tmp_path / "Data"
    root.mkdir()
    outside = tmp_path / "Data2"
    outside.mkdir()
    (outside / "secret").write_bytes(b"untouched")
    store = boundary(root)
    for name in ("../Data2/secret", str(outside / "secret"), "C:secret", "x:stream", "a\\b"):
        with pytest.raises(Problem):
            with store.open_read(name):
                pytest.fail("Opened an out-of-root path")


def test_read_create_and_identity_delete(tmp_path):
    store = boundary(tmp_path)
    store.mkdir("export-cache")
    with store.open_new("export-cache/one.zip") as out:
        out.write(b"dataset")
    with store.open_read("export-cache/one.zip") as incoming:
        assert incoming.read() == b"dataset"
    identity = store.inventory_entry("export-cache/one.zip")
    store.unlink_registered("export-cache/one.zip", identity)
    assert not (tmp_path / "export-cache/one.zip").exists()


def test_scan_does_not_follow_junctions(tmp_path):
    root, outside = tmp_path / "root", tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret").write_bytes(b"untouched")
    link = root / "jump"
    result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)], capture_output=True)
    assert result.returncode == 0, result.stderr
    store = boundary(root)
    assert store.inventory_entry("jump")["blocked"]
    with pytest.raises(Problem):
        with store.open_read("jump/secret"):
            pytest.fail("Followed junction")
    assert (outside / "secret").read_bytes() == b"untouched"


def test_hardlink_mutation_is_rejected(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "original"
    outside.write_bytes(b"keep")
    os.link(outside, root / "alias")
    store = boundary(root)
    with pytest.raises(Problem):
        store.unlink_registered("alias", store.inventory_entry("alias"))
    assert outside.read_bytes() == b"keep"


def test_root_replacement_invalidates_scan(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    store = boundary(root)
    root.rename(tmp_path / "old-root")
    root.mkdir()
    with pytest.raises(Problem):
        store.inventory_entry("file")


def test_locked_parent_cannot_be_replaced_during_access(tmp_path):
    store = boundary(tmp_path)
    store.mkdir("cache")
    (tmp_path / "cache/file").write_bytes(b"data")
    with store.open_read("cache/file") as incoming:
        with pytest.raises(OSError):
            (tmp_path / "cache").rename(tmp_path / "moved")
        assert incoming.read() == b"data"


def test_publish_verified_handle_and_reject_replaced_file(tmp_path):
    store = boundary(tmp_path)
    with store.open_new("stage") as stream:
        stream.write(b"archive")
    expected = store.inventory_entry("stage")
    store.publish("stage", "archive", expected)
    assert (tmp_path / "archive").read_bytes() == b"archive"
    with store.open_new("stage") as stream:
        stream.write(b"replacement")
    with pytest.raises(Problem):
        store.publish("stage", "other", expected)
    assert not (tmp_path / "other").exists()

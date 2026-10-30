import subprocess
import sys


def test_storage_report_requires_explicit_root():
    result = subprocess.run(
        [sys.executable, "-m", "visionlabel.cli", "storage-report"], capture_output=True, text=True
    )
    assert result.returncode != 0
    assert "--root is required" in result.stderr


def test_storage_report_writes_only_inside_root(tmp_path):
    from visionlabel.service import Service

    root = tmp_path / "server"
    srv = Service(root)
    srv.close()
    result = subprocess.run(
        [sys.executable, "-m", "visionlabel.cli", "storage-report", "--root", str(root)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert len(list((root / "reports/storage").glob("*.json"))) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["server"]

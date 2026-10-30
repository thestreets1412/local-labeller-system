"""Install the Phase 11 wheel into an isolated target using the existing Python."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

CHECK = """
import json, sys
from pathlib import Path
from array import array
import importlib.metadata, visionlabel
assert Path(visionlabel.__file__).is_relative_to(Path(sys.argv[1]))
from visionlabel.service import Service
from visionlabel.storage_inventory import scan_storage
from visionlabel.database import SCHEMA_REVISION
s = Service(Path('synthetic-root'))
try:
    s.bootstrap('smoke', 'synthetic-wheel-password')
    assert SCHEMA_REVISION == '0009'
    assert s.export_cache.policy()['max_bytes'] == 4*1024**3
    assert scan_storage(s.root)['complete']
finally:
    s.close()
import visionlabel_native
assert visionlabel_native.rgba_to_float(bytes([0,127,255,255])) == array('f', (v/255 for v in [0,127,255,255])).tobytes()
import dearpygui.dearpygui as dpg
from visionlabel.desktop import Desktop
app = Desktop('http://127.0.0.1:8765')
app.build()
for i in range(3):
    dpg.render_dearpygui_frame()
assert dpg.does_item_exist('storage_manager')
app.pool.shutdown(wait=True)
dpg.destroy_context()
print(json.dumps({'version': importlib.metadata.version('visionlabel'), 'schema': SCHEMA_REVISION, 'native_compatible': True, 'storage_ui_built': True, 'isolated_target_install': True}))
"""


def main():
    wheel = Path("rush-wheel/visionlabel-0.1.5-py3-none-any.whl").resolve()
    output = Path("docs/verification-artifacts/phase11/wheel-smoke.json").resolve()
    with tempfile.TemporaryDirectory(prefix="visionlabel-phase11-wheel-") as folder:
        target = Path(folder) / "site"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-deps",
                "--target",
                str(target),
                str(wheel),
                "--disable-pip-version-check",
            ],
            check=True,
        )
        env = os.environ.copy()
        env["PYTHONPATH"] = str(target)
        result = subprocess.run(
            [sys.executable, "-c", CHECK, str(target)], cwd=folder, env=env, text=True, capture_output=True
        )
        print(result.stdout)
        print(result.stderr)
        result.check_returncode()
        evidence = json.loads(result.stdout.strip().splitlines()[-1])
        evidence["wheel_sha256"] = hashlib.sha256(wheel.read_bytes()).hexdigest()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    sums = Path("rush-wheel/SHA256SUMS.txt")
    lines = [line for line in sums.read_text().splitlines() if wheel.name not in line]
    lines.append(evidence["wheel_sha256"] + "  " + wheel.name)
    sums.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

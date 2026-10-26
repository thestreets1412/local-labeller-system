# Install Phase 10 (VisionLabel 0.1.3)

Use Windows x64 and Python **3.12.10**. Close VisionLabel/DataTracking and back up
server data before upgrading. Upgrade both desktop and service environments when
separate. Service startup automatically applies migration **0008**.

From the repository root in PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Install-Phase10.ps1
.\.venv\Scripts\python.exe -I -m visionlabel.launcher
```

The script uses the existing `.venv`, or creates one if absent using `py -3.12`.
It checks Python's exact version, verifies wheel SHA256 checksums, downloads pinned
runtime dependencies from **https://pypi.org/simple** with pip/hash checks, installs
the local application/native wheels, and runs `pip check`. No global installation.
The app itself is supplied by this repository, not published to PyPI. Installation
needs Internet; normal runtime remains LAN-only. No uv, Rust or compiler is needed.

Choose another Python or environment:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\Install-Phase10.ps1 -Python C:\Python312\python.exe -Environment D:\VisionLabel\venv
```

Or call the Python installer directly:

```powershell
.\.venv\Scripts\python.exe .\scripts\install_phase10.py
```

For offline dependencies, add `--wheelhouse D:\wheelhouse` to the Python invocation.
Use `--skip-native` (PowerShell `-SkipNative`) to omit installing the extension;
this does not uninstall an extension already present.

Included wheels:

- **visionlabel-0.1.3-py3-none-any.whl**: Phase 10 application, API and migration.
- **visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl**: existing Rust/PyO3 texture
  accelerator, unchanged. Phase 10 creates no new native extension. Accept avoids
  redundant same-image raster decoding/upload while refreshing annotation state.
- Older application wheels are retained for identification. Do not install all
  application wheels together or downgrade a migrated live database.

If pinned dependencies are already installed, a direct pip upgrade is:

```powershell
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps --force-reinstall .\rush-wheel\visionlabel-0.1.3-py3-none-any.whl .\rush-wheel\visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl
```

See [Phase 10 evidence](../docs/phase10-plan.md) for behavior and remaining company
acceptance checks. Local wheel checks do not prove clean-machine/company readiness.

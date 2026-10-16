# Install packaged VisionLabel

Use **visionlabel-0.1.2-py3-none-any.whl** for export performance improvements and
Prepare/Save progress bars. Older wheels are retained for identification; do not
install every `visionlabel-*` wheel together.

Close VisionLabel and DataTracking and back up server data before upgrading.
In the Python 3.12 Windows x64 virtual environment already used for the application,
run from the repository root:

```powershell
python -m pip install --no-index --no-deps --force-reinstall .\rush-wheel\visionlabel-0.1.2-py3-none-any.whl
```

The optional display accelerator is unchanged. If not already installed:

```powershell
python -m pip install --no-index --no-deps .\rush-wheel\visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl
```

These commands assume runtime dependencies are already installed. For a new
environment follow README.md or the offline-kit instructions. No Rust or compiler
is needed to install these wheels. Upgrade both service and desktop environments
if separate. Start with `python -m visionlabel.launcher` in the same environment.

Check the actual code and extension loaded:

```powershell
python -c "import sys, visionlabel; from visionlabel import texture; print(sys.executable); print(visionlabel.__version__); print(visionlabel.__file__); print('Native display active:', texture._native_convert is not None)"
```

Version 0.1.2 automatically applies migration 0007 on service startup. Export
improvements are in the application wheel; the native wheel accelerates display
textures only. See `docs/export-performance.md` for measured scope and limitations.

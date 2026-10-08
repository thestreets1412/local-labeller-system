# VisionLabel application icon

The original mark combines an annotation rectangle, four resize handles and a V.
It identifies the annotation application; the V does not indicate that a dataset
or working export has been reviewed or approved.

The colors match the desktop: charcoal `#13171E`, mint `#4CC9A6`, and pale white
`#EEF7F4`. No fonts, external graphics, or runtime network resources are needed.
These project-authored assets use the repository's MIT license.

Assets in `src/visionlabel/assets`:

- `visionlabel.svg`: editable vector master with a square viewBox.
- `visionlabel-1024.png`: 1024 px master with transparent outer corners.
- `visionlabel-64.png`: desktop header texture, displayed at 24 px.
- `visionlabel.ico`: Windows RGBA icon with 16, 20, 24, 32, 40, 48, 64, 128,
  and 256 px frames for the title bar and running taskbar.

Regenerate all assets from the shared geometry with the existing environment:

```powershell
.\.venv\Scripts\python.exe scripts/build_brand_assets.py
```

The generator uses only Python's standard library and supersampled rasterization.
Keep its geometry and SVG definitions synchronized when changing the design.
The assets are included in the Python package by Hatch's package directory rule;
paths resolve relative to the installed module, independent of the working directory.
The desktop sets the Windows application ID to `VisionLabel.Desktop` before
creating its viewport. Existing user-created shortcuts are not modified. This
does not provide an executable or installer icon for the pending Nuitka package.

Verification on Windows (2026-10-08): Ruff and the existing desktop smoke passed,
including real HTTP import, rectangle save/reload, undo, recovery and autosave.
An offline wheel build included all four assets. Loading the module from that
wheel's extracted contents successfully rendered the header texture; Windows
`WM_GETICON` returned non-null handles for both the small and large viewport icons.
This used the existing development environment's dependencies, not a clean-machine
installation. Human mouse/DPI and pinned-shortcut acceptance remain unverified.

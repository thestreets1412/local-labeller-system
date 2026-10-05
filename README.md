# VisionLabel + DataTracking

English-only Windows annotation desktop with a local FastAPI service.
Current milestone: **Phase 7, YOLO prediction import and BMP correction workflow**.
Use **Import YOLO labels** in a detection project to preview/import same-stem `.txt`
files, then edit their saved rectangles directly. See [Phase 7 instructions](docs/phase7-plan.md).
See [operations guide](docs/operations-guide.md) and [Phase 6 status](docs/phase6-plan.md).
This is not yet a production Nuitka/LAN release.
The desktop includes polygon/QC and YOLO prediction import. Canonical split/export
and LabelMe import integration remain pending. See [Phase 5 progress and commands](docs/phase5-plan.md),
[Phase 4 progress](docs/phase4-plan.md) and [Phase 3 progress](docs/phase3-plan.md).
The user confirmed the Phase 1 workflow and DPI operation. Phase 2 team/review/LAN
acceptance and final release qualification are still open.
The user authorized starting Phase 3 while retaining unfinished Phase 2 work;
actual company-client/LAN/SMB testing is deferred until that environment is available.

## Start locally

Use **Windows x64 and Python 3.12.10**. Installation with Python's bundled **pip**
is supported; **uv is optional**. The bare `py` or `python` command may select a
different Python version, so check it first. If needed, replace `python` below
with the full path to the Python 3.12.10 executable supplied by IT.

From the repository root in PowerShell:

```powershell
# Check the interpreter before creating an environment:
python --version
python -c "import struct; print(struct.calcsize('P') * 8)"

# New clone only: create .venv if it does not already exist.
python -m venv .venv

# Install the application and pinned runtime dependencies:
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Start the local service and desktop together:
.\.venv\Scripts\python.exe -m visionlabel.launcher
```

The checks should print `Python 3.12.10` and `64`. Run all commands from the
repository root. An existing `.venv` should be reused, not recreated. Activation
is unnecessary when invoking its executable directly; no PowerShell execution
policy change or administrator installation is needed for the virtual environment.

`requirements.txt` includes the local application (`-e .`) and exact runtime
versions exported from `uv.lock`. After pulling dependency changes, run the same
pip install command again. Editable installation keeps application code linked to
this checkout, so keep the checkout in place. Installation downloads dependencies
and isolated build tools from PyPI or the index configured by IT. If that access
is unavailable, use the [offline kit](docs/operations-guide.md#offline-installation-kit).
The application itself does not require internet access at runtime.

For development tools, install `requirements-dev.txt` instead (it includes the
application and runtime requirements). If uv is already available, `uv sync --locked`
remains an alternative to pip; users do not need uv to consume either requirements file.

The first launch asks you to set an administrator password (at least 12 characters).
Sign in as `admin` in the desktop with that password. There is no default password.
Closing the desktop stops the service started by this launcher.

To use a different data directory:

```powershell
.\.venv\Scripts\python.exe -m visionlabel.launcher --root D:\VisionLabelData
```

The default data directory is `%LOCALAPPDATA%\DataTracking`. SQLite stays on its
local fixed disk; managed blobs and the import inbox are inside that directory.
Do not place it on SMB, a mapped network drive, OneDrive, or another cloud-synced folder.
Use a folder accessible only to the intended Windows account/administrators.

## Try the rectangle workflow

1. Generate 100 synthetic images, or copy JPEG/PNG/BMP files into the server inbox:

   ```powershell
   .\.venv\Scripts\python.exe -m visionlabel.cli samples
   ```

   Use `--root D:\VisionLabelData` here too if you chose a custom directory.
   The default inbox is `%LOCALAPPDATA%\DataTracking\inbox`.

2. In the desktop, choose **New project**, enter a name, a lowercase slug such as
   `parts-inspection`, choose `detection`, and enter comma-separated class names.
3. Choose **Import inbox**. Import runs in the background. **Last import report**
   shows the outcome for every file, including duplicates, invalid files and warnings.
4. Select an image and class. Use **R** and drag in any direction to draw a rectangle.
   The pointer becomes a crosshair with horizontal/vertical guides across the visible
   image. Guides disappear outside the image, in Select mode, and during Space+drag pan.
5. Use **V** to select/move a box. Drag a selected box's corner or edge handles to resize.
6. **Wheel** zooms around the pointer, **Space + drag** pans, and **F** fits the image.
7. **Ctrl+Z / Ctrl+Y** undo/redo; **Delete** removes the selected shape;
   **1–9** chooses a class and updates the selected shape; **A / D** navigates images.
8. **Ctrl+S** saves. Autosave runs two seconds after a completed edit.
   The revision display changes only after the server confirms the save.
9. Navigate away and back to verify the saved annotation. Dirty navigation asks
   whether to save, retain a recovery draft, or cancel.

For a genuinely empty detection image, select **Verified empty** after removing
all boxes. An unlabeled image is different from a verified-empty image.
For classification, create a separate `classification` project and choose one class
per image; its labels use the same revision/save/recovery protocol.

## Try polygons and working QC

1. Create a **segmentation** project and import images. Existing detection projects
   stay rectangle projects; task type is not changed in place.
2. Choose a class, press **P**, and click to add vertices. **Enter**, double-click,
   or clicking the first point closes the polygon. **Escape** cancels it.
3. Press **V** to select/move a polygon. Drag its vertex handles to change its outline.
   Double-click an edge to insert a vertex. Select a vertex and press **Delete**
   to remove it; **Delete shape** removes the entire polygon.
4. **Ctrl+Z / Ctrl+Y**, zoom/pan/fit, **Ctrl+S**, autosave and recovery work with
   completed polygons. An invalid vertex edit keeps the previous valid shape.
5. Open **Statistics / QC** to inspect saved class counts, statuses, verified-empty
   counts, resolution/format/group distributions and warnings. Save and Refresh
   to include recent edits; unsaved canvas changes are not counted.

Finish or cancel an unfinished polygon before navigating or saving. Unfinished
vertices are local UI state and are not included in autosave or crash recovery.
Tiny geometry is a warning, while intersecting/degenerate polygons are rejected.
The statistics window displays the first 200 warnings and the total warning count.
Working statistics are separate from future immutable dataset-version statistics.

## Preview split algorithms (developer tool)

The independent Phase 4 engine supports random, stratified, group and stratified-group
strategies, deterministic seeds, pinned assignments, leakage checks and tolerance
diagnostics. It has no production split button yet: released-version verification,
immutable split storage and desktop integration are still pending.

Try the supplied synthetic 16-image/8-group fixture with a new output filename:

```powershell
.\.venv\Scripts\python.exe -m visionlabel.split_preview --input tests/fixtures/splitting/source.json --config tests/fixtures/splitting/config.json --output "$env:TEMP\visionlabel-split-preview.json"
```

Expected result: train 8, val 4, test 4, with intact groups. This command writes
diagnostics only, never canonical split data. Existing output files are not overwritten.
`PASSED` verifies algorithm constraints on the supplied projection, not release
provenance or export readiness. See [the full contract and limitations](docs/phase4-plan.md).

## Manage users and project access

Restart the application to load the new **Team & users** button. Database migration
0003 runs automatically on service startup, preserving existing projects and labels.

1. Sign in as `admin`, open a project, then choose **Team & users**.
2. In **Accounts (administrator)**, choose **New account form**, enter username,
   display name and a password of at least 12 characters, then **Create account**.
3. Open **Project members** and choose the account directly from the **User** dropdown.
4. Choose `annotator` and click **Add / update role**. The member appears in the list.
5. Sign in with the new account through **Connection** to test its access.

Project roles are `viewer`, `annotator`, `reviewer`, and `maintainer`. Review actions
arrive in the next Phase 2 increments. Account creation alone does not grant access
to projects. Maintainers can manage their own project's members using a user ID
provided by an administrator; only administrators see the global account list.

Administrators can reset passwords, disable/enable accounts, and revoke sessions.
Password reset or disable invalidates old sessions and editing leases immediately.
Role changes revoke leases in that project. Revision conflicts require **Refresh**
before a new edit; transient failures offer **Retry last request** using the same key.
The last active administrator or project maintainer cannot be disabled/removed.

## What is implemented

- Project and stable initial class-schema creation; JWT-free opaque-token login.
- Safe JPEG/PNG/BMP inbox import, SHA-256 byte identity, duplicate reporting, pagination,
  filename search, status filtering, and original-raster EXIF policy.
- Rectangle creation, selection, moving, eight resize handles, zoom/pan, shortcuts,
  local undo/redo, single-label classification, and explicit verified-empty labels.
- Real edit leases, heartbeat, generation fencing, optimistic revision checks,
  idempotent saves and claim acquisition, immutable revision blobs and audit events.
- Durable-file-before-DB publication, lost-response retry with the same key,
  restart invalidation, and corruption errors rather than empty-data fallback.
- DPAPI-protected local drafts and image cache; revision-aware recovery comparison.
- Offline basic backup/restore and a single-process data-directory lock.
- Account administration and project membership UI/API, optimistic administration
  revisions, scoped lease revocation, and safe upgrade from the Phase 1 database.
- Polygon editing in segmentation projects and read-only saved working statistics/QC.
- An independent deterministic split planner and diagnostic CLI for frozen projections.

This development build remains **loopback-only**. LAN HTTPS, assignment UI,
submit/review workflows, class schema migration, canonical dataset versions/splits/exports,
canonical LabelMe import, and a Nuitka installer remain pending. YOLO detection
prediction import is available through Phase 7's desktop workflow.
Group/assignee/class browser filters are completed with their team/QC workflows;
Phase 1 currently exposes filename/status filters. No production training export
is generated from mutable working annotations. See the [Phase 2 progress and remaining work](docs/phase2-plan.md).

For later company setup, cloning source does not transfer your home database,
images, or recovery drafts. Use the verified backup/restore commands below if you
intend to transfer canonical data. Git clone also only includes committed and
pushed work; this working branch has not been committed or pushed by the assistant.

## Recovery and storage

Desktop tokens stay in memory. Private cache/drafts live under
`%LOCALAPPDATA%\VisionLabel\<server-user-scope>` and use Windows DPAPI protection.
Cache is bounded to 1 GiB and 30 days; drafts are retained until explicitly resolved
to avoid losing work. Archived comparison drafts have the `.archived-draft` suffix.
Raw temporary decode inputs are removed after decoding; use OS disk encryption
where required by your organization.

When the server is unavailable, continue editing locally. Shared saves stop after
lease failure. **Reload / reconnect** obtains a new claim and compares the draft's
base revision/hash/schema with the server. Matching drafts can be restored explicitly.
Stale drafts are shown beside current server content for manual reapplication;
there is no force-overwrite button. Using the server version archives the prior
draft instead of overwriting it with subsequent edits.

Images larger than 2048 pixels on either axis use a smaller display texture.
All box coordinates remain in the original raster; export/source bytes are never
re-encoded. Full-resolution tiled zoom is not part of this milestone.

## Backup / restore

Stop the local service first. These commands refuse to open an active data directory.
Use a different physical disk for real backup protection.

```powershell
.\.venv\Scripts\python.exe -m visionlabel.cli backup --destination E:\VisionLabelBackups\first-backup
.\.venv\Scripts\python.exe -m visionlabel.cli restore --backup-set E:\VisionLabelBackups\first-backup --destination D:\VisionLabelRestored
.\.venv\Scripts\python.exe -m visionlabel.launcher --root D:\VisionLabelRestored
```

Backup uses SQLite's backup API and checks every referenced blob. A backup is usable
only when `backup_manifest.json` says `COMPLETE`. Restore requires a new destination,
validates hashes/FKs, invalidates leases and revokes session tokens. Password hashes
are preserved; the claim-signing key is regenerated. Inbox files, desktop recovery
drafts and caches are not canonical and are not included in server backups.

## Development and checks

Install the pinned developer tools with pip before running these checks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
```

Maintainers changing dependencies must update `uv.lock` and regenerate both pip
files in the same change. The export commands use uv on the maintainer's machine
only; they are not part of end-user installation:

```powershell
uv export --locked --no-dev --no-hashes --no-header --format requirements-txt --output-file requirements.txt
uv export --locked --no-hashes --no-header --format requirements-txt --output-file requirements-dev.txt
```

These pip files pin package versions but omit artifact hashes because they include
an editable local project. The offline kit retains its separate hash-verified
wheel installation workflow. Isolated build-tool versions follow `pyproject.toml`;
the pip files freeze runtime/developer dependencies, not the build environment.

```powershell
.\.venv\Scripts\python.exe -m ruff check src tests scripts
.\.venv\Scripts\python.exe -m ruff format --check src tests scripts
.\.venv\Scripts\python.exe -m mypy src/visionlabel
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe scripts\desktop_smoke.py --output "$env:TEMP\visionlabel-desktop-report"
.\.venv\Scripts\python.exe scripts\package_smoke.py --output "$env:TEMP\visionlabel-package-report"
```

The desktop smoke runs a real rendered GUI against a real loopback server using
synthetic images and saves a screenshot/report. The package smoke provisions
hash-verified wheels first, then installs them **offline** into a separate environment.
It is not a clean-machine/Nuitka installer qualification.

To run desktop and service separately:

```powershell
.\.venv\Scripts\python.exe -m visionlabel.cli init
.\.venv\Scripts\python.exe -m visionlabel.cli serve
# In a second terminal:
.\.venv\Scripts\python.exe -m visionlabel.desktop
```

OpenAPI is available as local `/openapi.json` and frozen in `docs/contracts`.
Swagger/ReDoc CDN pages are disabled. The application makes no external runtime
requests; dependency and notice downloads are provisioning-only utilities.

## Engineering references

- [Product specification](VisionLabel_DataTracking_Specification.md)
- [Repository instructions](AGENTS.md)
- [Accepted baseline / implementation decisions](docs/adr/0001-phase1-baseline.md)
- [Requirement-to-test matrix](docs/phase1-verification.md)
- [Third-party notices](THIRD_PARTY_NOTICES.md)
- [Dependency inventory and native review](docs/license_inventory/native-review.md)

Source is MIT licensed. Dependency exceptions were explicitly approved by the user;
the final production installer still requires a complete artifact/license audit.

# Import performance increment — VisionLabel 0.1.1

Authorized 2026-10-15 for Import inbox and Import YOLO Labels. User workload:
approximately 5,400 images, 901 KB each, believed to be 640 x 640, stored on HDD,
with up to seven YOLO rectangles per image. This increment implements the import
priorities from `rust-extension-opportunity-survey.md`. Earlier phase/release and
company acceptance gaps remain open.

## Changes and integrity contracts

| Requirement | Implementation | Evidence |
| --- | --- | --- |
| IMP-PERF-01 | Store one import outcome per row; stop rewriting the growing report after each image. Assemble the final report once. | Running-job API and durable-row tests |
| IMP-PERF-02 | Commit a successful outcome/progress update in the same transaction as its image (plain inbox) or annotation (YOLO). Dry-run and invalid results use their own transaction. | Abrupt exit after committed result/save, injected rollback |
| IMP-PERF-03 | One case-insensitive filename-stem index per unchanged directory/job, shared by all images. Compare directory timestamps before use; rebuild on change, reject changes during scan. Recheck after decode and before prediction save. | Reuse, changed-directory and newly ambiguous sibling tests |
| IMP-PERF-04 | Reuse job-private scratch files sequentially, including truncation when the next image is smaller; remove scratch on normal completion. WIC still fully decodes every image, but inspection no longer copies RGBA into an unused Python bytes object. | Large/small BMP, corrupt raster and prediction tests |
| IMP-PERF-05 | Desktop polls `/jobs/{id}?compact=true`: running/queued responses omit results; terminal responses return the report. Default requests retain the existing full-result API behavior. | Compact/full polling tests and desktop smoke |
| IMP-PERF-06 | Add stage timings and directory scan counts to successful job reports. | Real synthetic service benchmarks |
| IMP-DIST-01 | Build application version 0.1.1 as a wheel and include it in an offline pip kit. Existing optional native 0.1.0 wheel remains compatible. | Wheel and kit checks |

The service remains the canonical writer. Permission/schema rechecks, leases,
fencing, expected revisions, annotation validation, source hashes, durable file
publication and SQLite synchronous FULL remain enabled. No prediction overwrites
an existing annotation. Same bytes already deleted from a project stay deleted.

Migration **0006** adds `import_results(job_id, ordinal, result_json)`. It does not
rewrite old jobs, annotation bytes or image assets. Old job reports remain readable.
For interrupted new jobs, the API reconstructs the report from committed outcome
rows even when the final report was never assembled. Startup still marks interrupted
jobs failed; it does not automatically resume them. A crash between initial image
commit and prediction save can retain an unlabeled image, as before; no successful
prediction is reported until its annotation and outcome are committed together.

Directory timestamp checks detect normal concurrent additions/removals, not an
adversarial directory snapshot. Existing per-file change/path checks still apply.
Do not copy/rename source pairs while importing. A hard process exit can leave
job scratch files, which are noncanonical; no managed DB pointer references them.

## Timings

The final import report contains `performance.elapsed_seconds`, `directory_scans`
and `stage_seconds` with read/header/hash, label preparation, staging/decode,
asset publication/commit, prediction claim/save/release and progress handling.
`item_total` overlaps its per-stage breakdown; do not add it to those stages.
Stage timings cover completed stages; failed work may only appear in item_total.
Elapsed timing is captured before final report serialization and final job commit.

`scripts/benchmark_import.py` exercises real service imports, original image
publication, decoding, database writes and optional seven-box prediction saves.
Its 640 x 640 BMPs are 1,228,854 bytes each, with unique pixels per image.
Fixture creation, GUI and HTTP polling are outside its timer. Temporary fixture
data is automatically removed; only aggregate reports are retained. These are
local diagnostic runs, not acceptance results for the user's 5,400-image dataset.

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_import.py --count 1000 --mode inbox --output dist/import-inbox.json
.\.venv\Scripts\python.exe scripts/benchmark_import.py --count 1000 --mode yolo --output dist/import-yolo.json
```

The main gains are less repeated work and fewer durable commits; they are in the
application wheel. This increment does not add a Rust parser: matching the user's
37,800 boxes took only 2.668 seconds in the earlier synthetic parsing survey.
The existing native wheel still accelerates display texture conversion.

### Local comparison

One run per mode/version, 200 unique 640 x 640 BMPs, seven rectangles per YOLO
file, same synthetic generator and local host. The baseline uses `service.py`
and `imaging.py` from the Git commit identified in the evidence JSON, loaded
from an isolated package copy. This is a diagnostic comparison, not a repeated
or isolated benchmark; filesystem cache and background activity can affect it.

| Mode | Baseline | Final implementation | Lower elapsed time |
| --- | ---: | ---: | ---: |
| Import inbox | 44.134 s | 38.356 s | 13.09% |
| Import YOLO Labels | 81.848 s | 67.848 s | 17.10% |

YOLO built its directory index once. Separate progress handling took 0.055 s in
the final YOLO run because successful outcomes commit with their annotations.
Asset publication and annotation claim/save/release still dominate, so this
increment does not claim an order-of-magnitude end-to-end improvement. The larger
5,400-image dataset has not been timed. Full data and measured stage totals:
`docs/verification-artifacts/import-performance.json`.

## Installation

Stop the desktop and DataTracking service. Back up the existing server data using
the verified backup workflow before the schema upgrade. On the existing Python
3.12 environment with runtime dependencies already installed, run:

```powershell
python -m pip install --no-index --no-deps --upgrade .\visionlabel-0.1.1-py3-none-any.whl
```

Optionally install the existing display accelerator:

```powershell
python -m pip install --no-index --no-deps .\visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl
```

Upgrade the **DataTracking service environment** as well as desktop installations.
Restart the service to apply migration 0006, then open the desktop. Users do not
need Rust, Cargo, maturin or uv. For a new installation use the complete offline
kit, which includes locked runtime dependencies and the existing installer.
Follow `docs/operations-guide.md` for the new-install kit procedure.

Developer build:

```powershell
uv build --wheel --out-dir dist/import-improvements/wheels
.\.venv\Scripts\python.exe -m maturin build --release --locked --manifest-path native/texture/Cargo.toml --interpreter .venv/Scripts/python.exe --out dist/import-improvements/wheels
.\.venv\Scripts\python.exe scripts/build_offline_kit.py --output dist/import-improvements/offline-kit --native-wheel dist/import-improvements/wheels/visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl
```

The kit is an unsigned development distribution; fresh-company-machine/LAN/HDD
acceptance remains pending. The application wheel includes migration 0006 and
the retained third-party notices. Python and Cargo lockfiles remain reproducible.

## Final local verification (2026-10-15)

- Full regression suite: 298 passed; one existing Starlette TestClient deprecation warning.
- Ruff lint and formatting passed; mypy passed for 42 source files.
- Rendered desktop smoke passed, including real HTTP inbox/YOLO import, saved
  annotation reload, export and image deletion confirmation.
- Installed both final wheels into an isolated target and exercised native
  conversion plus real inbox and YOLO service imports with PATH empty (no Rust
  toolchain available to those processes). Migration 0006 loaded from the wheel.
- Final offline kit verified all 81 file checksums. Local distribution artifacts
  are under `dist/import-improvements/wheels` and
  `dist/import-improvements/offline-kit-final`; build outputs are not tracked.

These checks do not replace human mouse/DPI acceptance or the pending company
LAN and actual 5,400-image HDD workload checks.

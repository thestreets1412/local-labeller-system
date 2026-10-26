# Project image removal and navigation acceleration

Authorized 2026-10-15. This increment does not close earlier phase, release or
company/LAN acceptance gates.

## Requirements and behavior

- IMG-DELETE-01: Maintainers can use **Delete image...**, then **Yes, delete image**
  or **No, keep image**. The Delete keyboard shortcut still deletes annotations.
  The dialog names the image and explicitly warns about discarding unsaved edits.
- IMG-DELETE-02: Removal is permanent within the project UI. Immutable assets,
  annotation/review evidence and existing snapshots remain intact. It does not
  erase the import source folder or delete another project's copy. There is no
  restore endpoint. Reimport of the same bytes into that project reports
  `IMAGE_DELETED`; other projects may still import those bytes.
- IMG-DELETE-03: `DELETE /api/v1/images/{image_id}` requires an Idempotency-Key,
  expected content/state revisions and project maintainer permission (system
  admin alone is insufficient). An active claim requires its current owner/token/
  generation. With no active claim, deletion is allowed in the same serialized
  transaction. It fences claims, increments state and project revisions, audits
  the removal, and records idempotent success. Ordinary image endpoints return
  404 afterwards; future working snapshots exclude it. Historical snapshots keep
  their immutable references. No DB migration is needed: `images.archived` is
  the irreversible image tombstone, independent of reversible project archive.
- IMG-PERF-01: Replace the per-channel Python loop used by all image opens
  (including A/D and post-review S) with an optional Rust/PyO3 texture conversion.
  Windows WIC decoding, raw raster coordinates, EXIF policy, thumbnail sizing,
  permissions, lease acquisition and fresh annotation/review reads are unchanged.
  Native output has exactly the same float32 bytes for all 256 channel values.
  Conversion releases the Python GIL and accepts at most 2048 x 2048 RGBA pixels.
- IMG-DIST-01: Distribute the accelerator as a CPython 3.12 / Windows x64 wheel.
  End users need neither Rust nor maturin. The application remains functional
  using the Python fallback without this optional wheel.

## Build and install

From the repository root, on the developer machine with MSVC Rust tooling:

```powershell
.\.venv\Scripts\python.exe -m maturin build --release --locked --manifest-path native/texture/Cargo.toml --interpreter .venv/Scripts/python.exe --out dist/native
uv build --wheel --out-dir dist/native
```

The native crate pins PyO3 in Cargo.toml and every transitive crate in Cargo.lock;
the dev Python lock pins maturin. The optional wheel is installed explicitly,
so the base runtime requirements do not trigger a source build on user machines.
Install into the destination's existing Python 3.12 environment with bundled pip:

```powershell
python -m pip install --no-index --no-deps --force-reinstall .\visionlabel-0.1.0-py3-none-any.whl .\visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl
```

This upgrade assumes the application's runtime dependencies are already installed.
For a complete offline kit, pass the prebuilt native wheel:

```powershell
.\.venv\Scripts\python.exe scripts/build_offline_kit.py --output D:\VisionLabel-Kit --native-wheel dist/native/visionlabel_native-0.1.0-cp312-cp312-win_amd64.whl
```

Restart the desktop and service after upgrading. Wheels/build output stay ignored.
This remains an unsigned development installation, not production packaging or
proof of clean-company-machine compatibility.

## Verification

`tests/test_image_delete.py` covers tombstones, immutable evidence, shared assets,
idempotency, stale revisions, lease tokens, permission failures and reimport.
`tests/test_texture.py` compares exact float bytes and tests fallback/input limits.
`scripts/desktop_smoke.py` exercises rendered confirmation/cancel/delete using
synthetic images and real HTTP, plus the existing rectangle/save/reload checks.
`scripts/benchmark_texture.py` measures five conversion trials on synthetic
2048 x 2048 RGBA bytes. These results measure conversion only, not disk/HTTP/WIC/
GPU upload or end-to-end navigation. Human mouse/DPI and company LAN acceptance
remain outstanding.

Build tooling references: [PyO3](https://pyo3.rs/v0.27.2/),
[maturin distribution guide](https://www.maturin.rs/distribution.html).

## Local evidence (2026-10-15)

- Final full regression: 289 passed in 104.43 seconds. One existing Starlette
  TestClient/httpx deprecation warning; no test failures.
- Five-trial conversion median: Python 2.9809 seconds; Rust 0.098825 seconds;
  30.16x for conversion alone. Raw samples: `dist/native/benchmark.json`.
- Real desktop/HTTP smoke passed, including confirmation, cancel and delete.
  Report and rendered dialog: `dist/image-improvements-smoke/`.
- Native wheel installed with pip and imported in an isolated subprocess with
  an empty PATH, excluding Rust/cargo/maturin lookup. This is not a clean-machine
  OS compatibility test.
- Offline kit with the native wheel built successfully; all 81 manifest files
  passed integrity verification. Output: `dist/image-improvements-kit/`.
- Ruff lint, changed-file formatting, mypy (40 source files), Rust clippy and
  exact-byte native/fallback tests passed. Repository-wide formatting also found
  pre-existing formatting differences in `scripts/build_brand_assets.py`, which
  this increment does not change.
- Wheel hashes and sizes: `dist/native/artifacts.json`. Native notices are
  included and wheel files inspected. These artifacts are local build outputs.


## Phase 10 controlled restoration (2026-10-27)

Version 0.1.3 adds a deliberate exception to the original deletion policy above:
a maintainer can restore image membership from an accessible same-project dataset
checkpoint. Restore previews the full change, creates a safety checkpoint, fences
old claims and appends new annotation revisions requiring review. It does not
remove tombstone/history evidence or provide a general undelete endpoint. Ordinary
reimport of a deleted image still reports IMAGE_DELETED. See phase10-plan.md.

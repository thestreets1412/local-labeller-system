# Phase 1 baseline (2026-10-03)

Accepted by the user: rectangle usability first, English-only application text,
existing .venv / Python 3.12.10, the specification's persistence guarantees,
explicit contracts and serialization vectors, early packaging and recovery checks.
Phase 0 foundations are prerequisites included in this implementation effort.
The specification's A01–A12 remain applicable; no direct desktop canonical writes.

The initial product milestone is import -> claim -> rectangle -> save -> reload,
followed by usable selection, resizing, pan/zoom, history, autosave, recovery,
and single-label classification. Phase 2 team/review UI and Phase 3–6 capabilities
are not implicitly included in this milestone. No requirement is silently removed.

## Serializer profile vl-json-1

Decimal values are quantized half-even to six places, emitted without exponent or
trailing fractional zeros (1.0 becomes 1), negative zero becomes 0. Keys sort by
Unicode code point; UTF-8, no BOM, no final newline, compact separators. Arrays
retain order except shapes and image_labels sorted by ID. Finite attribute numbers
use the same numeric representation. Geometry is checked after quantization.
Tests pin exact bytes, not a reimplementation of the serializer.

## Image decoder selection

The stock OpenCV wheels include LGPL FFmpeg (see upstream opencv-python packaging
documentation), conflicting with this repository's distributed-core policy.
Use Windows Imaging Component, supplied by Windows, for JPEG/PNG decoding and
stdlib array for texture conversion. This is the decoder fallback allowed by spec 3.2;
there is no bundled third-party codec. No automatic EXIF transform is applied.
OpenCV is not installed. Windows remains the v1 deployment prerequisite.
https://pypi.org/project/opencv-python-headless/

## Environment and dependency control

uv.lock is the exact dependency lock; uv sync --locked uses the existing .venv.
Development is loopback HTTP only. The app must not bind a public/LAN interface
until the Phase 2 HTTPS and permission deployment gate is complete.
Runtime data defaults to the user's local application-data directory, never Git.

User-approved dependency exceptions (2026-10-03): certifi MPL-2.0,
typing_extensions PSF-2.0, and NumPy's 0BSD/Zlib/CC0 components, with retained
notices and exact-version inventory. This does not permit arbitrary additional
copyleft dependencies. The stock OpenCV/FFmpeg exclusion remains unchanged.

The inspected NumPy 2.5.3 Windows wheel additionally bundles OpenBLAS/GCC runtime
and MSVC DLLs. Its wheel notice declares GPL-3.0-or-later WITH GCC-exception-3.1,
outside the specifically approved exceptions. Phase 1 does not need numerical
linear algebra, so NumPy is removed from the runtime instead of expanding the
license exception. Reconsider an eligible NumPy build only if a later feature
needs it; the approved 0BSD/Zlib/CC0 exceptions remain recorded.

Windows Tahoma is loaded from the installed OS for English and Thai user-data
glyphs. It is not copied or redistributed, and no font download occurs. The
Dear PyGui embedded default font is the fallback when Tahoma is unavailable.

The user additionally approved FreeType's FTL option as bundled in Dear PyGui
on 2026-10-03. Retain FTL attribution and notices; do not select the GPL alternative.

## Phase 1 implementation layout and operational scope

Use a single installable src/visionlabel package with independent domain, canvas,
contracts, storage, service, API, client, desktop and operations modules. These
map to the specification's module responsibilities without empty package trees.
Future phases can split large modules while preserving dependency boundaries.
SQLAlchemy connections plus explicit SQL implement short compare-and-swap
transactions; Alembic owns schema versioning. Initial setup is loopback-only.
Basic backup/restore is brought forward from Phase 3 to protect pilot data.
Backups require the service to be stopped in Phase 1; scheduled maintenance-mode
backup, production packaging and two-PC operations remain in their specified phases.

JPEG/PNG decode runs in a resource-limited worker during import (20 seconds per
image, 768 MiB process memory, 40 megapixel/50 MiB input limits). The desktop uses
a maximum 2048-pixel display texture while coordinates always use the original
raster dimensions. Smaller previews are display-only; raw assets remain unchanged.

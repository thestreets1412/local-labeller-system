# Phase 5: format conversion and legacy dry-run

Status: independently runnable format primitives and read-only migration diagnostics.
**The Phase 5 exit gate is not complete.** There is no desktop export/import action,
production training dataset, canonical import transaction or READY export record yet.

## Sequence and requirement mapping

The user requested Phase 5 after the split-engine increment. This authorizes an
independent format increment; earlier implementation gaps remain open.

| Requirement | This increment | Remaining destination |
|---|---|---|
| PR16, §15.3–15.5 | Exact YOLO detection/segmentation bytes, polygon-to-bbox loss option, safe classification folder mapping, train coverage and YAML generation | Phase 5 dataset materialization, release/split verification, jobs, staging/publication and GUI |
| PR17, §15.2 | LabelMe rectangle/polygon and YOLO detection parsers; explicit mapping, actual image decode, contained paths, per-file read-only dry-run | Phase 5 canonical revision1 import, existing-data conflict checks, permissions, provenance audit and GUI |
| PR13, PR15, §15.6 | Preview explicitly disclaims provenance; no current DB data is substituted for releases | Phase 3 release and Phase 4 immutable split integration before production export |
| PR10 | Imported candidates are never APPROVED | Phase 2 revision-bound review prerequisite |
| PR04/08/09/12/18, PR02/14 | Earlier unfinished work remains in phase2/3/4 plans | Respective phase follow-ups; physical company-client tests deferred as authorized |

## Frozen format behavior: vl-formats-1

- Explicit class UUID to schema export_index mapping; never use UI array order.
- Original raster coordinates, no rotation or image transformation. Annotation
  normalization retains the existing six-decimal contract; normalized YOLO output
  uses Decimal half-even **nine** places, UTF-8 and LF, ordered by shape UUID.
- Revalidate rounded rectangle edges/positive area and exact rounded polygon
  intersections, repeated vertices and area. Unrepresentable geometry errors carry
  image/shape IDs. Verified-empty produces zero bytes; unlabeled is rejected.
- Segmentation stays polygon output by default. `polygon_to_bbox=true` is explicit
  and reports loss per shape; rectangle-to-polygon conversion is unsupported.
- Classification folder names use fixed width >=4 digits plus sanitized stable key;
  the unique numeric prefix prevents Windows case-fold collisions. Mapping records
  internal class ID, schema index and consumer order separately. The future writer
  must create all mapped class directories to preserve that order. Evaluation
  classes missing from train fail. Classification content requires one label.
- YAML names use quoted JSON strings (YAML-compatible), preventing newline/colon
  injection. Require every historical index from zero through the maximum, including
  inactive slots with their original names (§13.5); never compact or invent missing
  names. Preview omits unrepresented test/val partitions and warns for no val;
  the production adapter must derive this from verified split ratios.
- LabelMe only supports the explicit task's shapes. Unknown fields, nonempty flags,
  grouping and descriptions are errors rather than discarded metadata. Embedded
  imageData is disabled. Empty LabelMe annotations remain UNLABELED.
- YOLO input requires exactly five fields, known integer class, finite normalized
  coordinates and positive in-bounds rectangle. Missing labels remain UNLABELED;
  empty files become verified-empty only with `empty_is_verified=true`.
- Dry-run resolves LabelMe imagePath relative to JSON under source-root, rejects
  escapes/reparse paths and dimension mismatches. It decodes a temporary snapshot
  of the hashed raw bytes using the existing isolated WIC worker. Nonidentity EXIF
  orientation is rejected for explicit preprocessing/new asset selection.
- Read limits: 8 MiB request/label, 50 MiB image, 40 MP raster, 1000 input entries.
  Candidate shape IDs are deterministic UUID5 from source identity and ordinal.
  Any failed file has no partial content in the report; other files still report.

## Run the developer tools

From the repository root, generate a **new** report path:

```powershell
.\.venv\Scripts\python.exe -m visionlabel.format_preview export-preview --input tests/fixtures/formats/export-preview.json --output $env:TEMP\visionlabel-format-preview.json
```

The JSON contains label text, byte count, SHA-256, warnings and YAML. It is a format
preview, not an image dataset. It has `canonical_export=false` and
`provenance_verified=false`. No image bytes or source approvals are verified here.
For segmentation use `task: segmentation` and polygon content. For classification
use `task: classification`, one `image_labels` UUID per item and no shapes; the
report contains the folder mapping. Classes require `class_id`, `export_index`,
`name`, and (for classification) stable `key`.

Example migration request (class UUID must be explicitly replaced with the target
class; these are candidate mappings, not membership/DB checks):

```json
{
  "format": "yolo-detection",
  "task": "detection",
  "mapping": {"0": "10000000-0000-4000-8000-000000000001"},
  "empty_is_verified": false,
  "items": [{"image": "images/example.png", "label": "labels/example.txt"}]
}
```

```powershell
.\.venv\Scripts\python.exe -m visionlabel.format_preview import-dry-run --source-root D:\LegacyData --input D:\LegacyData\request.json --output $env:TEMP\visionlabel-import-report.json
```

For LabelMe use `format: labelme`, task detection/segmentation, map label strings
instead of numeric indices, and supply JSON as `label`. Paths use relative `/`
notation. Omitting a YOLO label or naming a missing file yields UNLABELED; it is not
proof of a negative example. Reports include source/image hashes, mapping/options,
candidate content/state and per-file errors. `canonical_import=false` and
`database_conflicts_checked=false` are always present; VALID only means syntax and
geometry passed. No server data is read or written and existing annotations cannot
be overwritten. Exit 0=report success, 2=per-file failures, 1=invalid request/I/O.
Existing output files are never overwritten.

## Verification and unfinished exit gate

`tests/test_formats.py` uses independent exact-byte expected rows, a separate
Decimal inverse for geometry tolerance, quantization-collapse/boundary cases,
classification ordering/coverage, unsupported legacy content, actual PNG decode,
path containment, per-file reporting and CLI no-overwrite checks. No Ultralytics,
LabelMe, YAML or additional runtime dependency is installed.

Verification on 2026-10-04: **141 tests passed** (37 Phase 5 cases), Ruff lint and
format checks passed for 46 files, mypy passed for 29 source files. The existing
Starlette TestClient/HTTPX deprecation warning remains. Offline wheel smoke passed
outside the checkout, including migration, desktop render, split preview and the
new format preview. This is development-machine wheel evidence, not a clean-machine
Nuitka installer test. The format report at
`verification-artifacts/format-preview-v1.json` has SHA-256
`9eb66d0084f0e31e77c4d26309d1b355ae1369a44cabf71b6613b48bdfc004f5`.
The installed wheel produced the same report hash. Package evidence is in
`verification-artifacts/package-smoke.json`. GUI behavior was unchanged this round;
physical company-client/LAN/SMB acceptance remains deferred.

Still required: full portable image/folder materialization and per-file manifests,
immutable asset-byte equality against released inputs, pinned approval evidence,
format/options/version/split hashes, copy-not-hardlink, staged atomic publication
with authorization recheck, runtime absolute-path YAML helper, and canonical
import's no-overwrite transaction/audit. These are implementation gaps, not merely
unavailable company tests. Desktop buttons wait for these integrations.

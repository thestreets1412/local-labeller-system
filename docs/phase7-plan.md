# Phase 7: model predictions and BMP workflow

User feedback, 2026-10-06: installed at the company, imported real prediction images
and YOLO text, and corrected boxes successfully. This confirms that specific human
workflow, not every negative case, reload scenario or format variant. Phase 8 now
adds working-dataset export for external training; earlier review/LAN gates remain open.

User-requested scope: label a small seed dataset, train externally, infer the remaining
images externally, then import same-stem YOLO detection labels directly for correction.
Example: `spring_img.bmp` and `spring_img.txt` in the same inbox subfolder.

Existing baseline: JPEG/PNG only in the application. Phase 5 has a YOLO parser and
command-line dry-run, but no canonical import or desktop action. This phase connects
that parser to real revision persistence and the editor, and adds BMP decoding.

- PR03: support BMP alongside PNG/JPG/JPEG with byte-signature/dimension checks,
  isolated Windows WIC decode, original immutable bytes and original coordinates.
- PR17: explicit numeric class mapping, same-folder/stem pairing, preview and import
  buttons, per-file report, strict five-field YOLO detection parsing, no LabelMe
  conversion or runtime dependency required.
- PR08/09/11/12: missing label stays unlabeled; empty label is verified-empty only
  by explicit option. Save candidates through real claims and expected revisions;
  refuse existing annotations, preserve editable revision history and source hashes.
  Predictions remain IN_PROGRESS, never automatically approved.
- Reject ambiguous same-stem image pairs, invalid/unknown classes and invalid
  coordinates rather than silently dropping rows. Keep ordinary image import usable.

Verification: synthetic BMP raster orientations/decode and raw byte preservation;
API preview -> import -> load -> edit -> save -> reload; conflicts/reimport,
invalid labels, missing/empty labels, mapping, authorization and UI smoke.
Training/inference remains external. Existing Phase 2–6 unfinished work remains
tracked in those plans; this feature does not declare those phases complete.

## Use it

1. Open a **detection** project. Import requires project maintainer or administrator.
2. Copy images and corresponding labels into the service's configured `inbox`.
   Subfolders are supported: `batch1/spring_img.bmp` pairs only with
   `batch1/spring_img.txt`. Keep the seed images already labeled out of this batch
   if you do not want their expected "annotation exists" reports.
3. Choose **Import YOLO labels**. Map each numeric index used by your model to an
   exact project class name, one line such as `0=Spring`, `1=Defect`. Initial values
   show project export indices; check them against the model's class order.
4. Choose **Preview** and inspect **Import report**. No images or annotation
   revisions are created by preview. It still creates an auditable import job.
5. Open the dialog again and choose **Import predictions** with the same mapping.
   The operation rereads source files; preview is not a reservation or frozen input.
6. Open an imported image, adjust boxes/classes as usual, and save. Imported boxes
   are revision 1; your correction creates revision 2. Reload preserves geometry.

Text is UTF-8 (BOM accepted), exactly five whitespace-separated fields per nonempty
line. Coordinates are normalized 0..1 using raw image dimensions. A sixth confidence
field is rejected: export YOLO labels without confidence. Multiple rows are multiple
rectangles. Unknown indices, nonfinite coordinates, out-of-bounds or zero-area boxes
reject that entire file. Empty `.txt` only means verified-empty if the checkbox is
explicitly enabled; missing files always stay UNLABELED. This path handles detection
rectangles; segmentation/classification projects reject it.

Images already present with revision 0 may receive predictions if no editor owns
the lease. Images with any annotation revision are reported as conflicts, including
repeated imports; user corrections are preserved. New images and prediction saves
are separate service transactions: a later lease/schema/save conflict can leave the
image imported but labels unsaved, reported as `image_retained=true`,
`label_state=NOT_IMPORTED`. Retry after resolving the conflict. A process interruption
may similarly leave a revision-0 image, which is safe to retry. Save rechecks all
permissions, expected revisions, schema and lease in its final commit transaction.
Audit records bind label path/hash, asset hash, mapping/options and import job ID
to the annotation save. Import never automatically approves predictions.

Each selected image gets a report with label path/hash, shape count and state where
available. TXT files without any matching supported image are not selected by the
image inbox scan. Only same-directory pairing is supported; for separate `images/`
and `labels/` trees, copy each label beside its image before importing. Multiple
image extensions with the same stem in one directory are rejected as ambiguous.

## Image format survey and support

| Extension | Before Phase 7 | Current support |
|---|---|---|
| `.png` | Supported | Single-frame PNG, unchanged raw bytes |
| `.jpg`, `.jpeg` | Supported | JPEG; no automatic EXIF rotation |
| `.bmp` | Rejected by scanner/header validation | BMP through Windows WIC, including top-down/bottom-up raster handling |
| `.tif`, `.tiff`, `.webp`, `.gif`, `.heic`, RAW | Not supported | Still rejected/not scanned; not promised by this phase |

Extensions are case-insensitive on the supported Windows filesystem. Header signatures
determine actual format and dimensions; WIC must fully decode successfully before
import. Limits remain 50 MiB and 40 MP per image; animation/multiframe is rejected.
BMP accepts supported DIB headers with 1/4/8/16/24/32-bit pixel depths at header level;
codec support is checked by actual decoding, so malformed/unsupported variants fail
with an explicit report. Bitmap row storage order never changes displayed annotation
coordinates. No third-party image runtime or dependency was added.

Phase 5's YOLO detection dry-run is now connected to a canonical desktop import;
its LabelMe canonical import, production export and earlier review/release work remain
pending. Phase 6's previously generated offline kit predates this feature; rebuild
the kit for deployment rather than distributing that old artifact as Phase 7.

## Verification evidence

- Full existing suite plus initial Phase 7 tests: **172 passed**. After the final
  mapping-retention/UI and error-report changes, the focused Phase 7 suite passed
  **16 cases**, including four additional BMP/Unicode/task checks. The existing
  Starlette TestClient/HTTPX deprecation warning remains.
- Tested BMP: 24-bit bottom-up/top-down with padded scanlines, 8-bit indexed palette,
  32-bit RGB and Unicode/case-insensitive paths. Full image bytes and pixel colors
  have independent expected values; row order is verified directly.
- Real HTTP/rendered desktop smoke passed: explicit mapping (model index 0 mapped
  to the second project class), preview without creating images, mapping retained
  for import, BMP display, revision1 predictions, correction/save/reload revision2.
- Offline wheel install outside the checkout passed migration, desktop rendering,
  split and format CLI checks. This is a wheel smoke, not company deployment.
- Ruff lint/format passed (51 Python files); mypy passed (29 source files).
- Evidence under `verification-artifacts/phase7/`: `desktop-smoke.json`,
  `yolo-import-dialog.png`, `bmp-prediction-workspace.png`, `package-smoke.json`.
  API snapshot: `contracts/phase7-openapi.json`; earlier snapshots are preserved.

Automated checks use synthetic fixtures. Human acceptance with the actual factory
BMP/prediction files and multi-PC/LAN testing still belongs to the company pilot.

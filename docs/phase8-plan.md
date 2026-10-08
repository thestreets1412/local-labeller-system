# Phase 8 — Working YOLO training export

2026-10-07 follow-up authorization: export failure diagnostics, class mapping and
project management/version organization are planned in
[`phase8-follow-up-plan.md`](phase8-follow-up-plan.md). Begin with aggregate
geometry diagnostics; later increments retain separate exit gates.

Follow-up P8-A through P8-F are locally implemented: diagnostics/navigation/history,
bounded quantization, explicit model mappings, project organization/templates and
revision-bound remapping. See the follow-up plan for evidence, migration `0004`,
format `vl-formats-2` and remaining company/physical acceptance and earlier phase gaps.

User authorization: 2026-10-06. The user successfully imported factory prediction
files and corrected their boxes. They now request usable training datasets for
detection, segmentation and classification, selectable validation/test percentages
and a destination on the computer running the desktop. Single-PC admin operation
must work. Home hotspot tests found no laptop-to-laptop connectivity; actual LAN
acceptance returns to the company environment after LAN implementation.

## Scope override

PR15/PR16: add a **working export**, freezing saved heads/schema/groups in one DB
snapshot and verifying referenced immutable files. It may contain IN_PROGRESS
predictions and is explicitly not a reviewed dataset release or canonical Phase 4
split. PR10/PR13 approved releases and the original Phase 2–6 gates remain open.
This is the user's change to the former release-only export sequence, not an
implicit approval of all labels. Users must inspect model predictions before training.

## Contract

- Admin/maintainer creates an idempotent background job; capture saved revisions
  in its persisted payload. Unlabeled/incomplete images are listed as excluded.
  Invalid/corrupt saved content blocks export, rather than silently losing objects.
- Validation 1–99%, test 0–98%, sum below 100; train gets the remainder. A nonzero
  partition must contain images. Small/grouped datasets may have rounded ratios.
- Deterministic seeded allocation keeps transitive equal-group/equal-asset components
  together, guarantees every observed class occurs in train or fails explicitly,
  and reports requested/actual counts plus per-class presence. No fabricated release ID.
- Copy original image bytes, normalized YOLO rectangles/polygons or classification
  directories. Unique image UUID filenames avoid collisions; manifest preserves originals.
- Server prepares a hash-checked archive in an export cache; desktop downloads to a
  private sibling staging directory, verifies hashes, then publishes to a **new**
  destination. Neither component overwrites an existing destination or source labels.
- Include manifest, exclusions, class mapping, portable data.yaml for detection/segment,
  a local-path YAML helper and training instructions. Classification uses the dataset
  directory and observed classes in stable numeric order. No Ultralytics runtime bundled.
- Recheck permissions before publication and download. Interruptions/failures cannot
  report a partial dataset as complete. Cached archives are derived and excluded from
  canonical backup; restore preserves jobs but missing archives require a new export.

## Implemented workflow

- `POST /api/v1/projects/{id}/working-exports` captures a saved snapshot and queues
  an idempotent background job on the existing bounded worker. `GET /jobs/{id}`
  reports completion; `GET /working-exports/{id}/download` checks permissions and
  archive integrity before streaming. No DB migration or new dependency is required.
- Desktop **Export YOLO** provides whole-percent validation/test inputs, seed,
  preparation, actual partition and per-class counts, exclusions and a directory picker.
  Unsaved current edits or unfinished polygons must be resolved before opening it.
- Working allocation uses the existing transitive group/asset component helper with
  its own versioned `working-yolo-export-1` algorithm. It covers rare classes in train,
  assigns remaining components by squared distance to integer targets with seeded ties,
  and repairs empty requested partitions only without breaking real-class train coverage.
  Verified-empty is reported separately and does not require background in train.
  This is deterministic allocation, not a claim of optimal stratification.
- Classification exports observed classes only, with stable index-prefixed folder names;
  its mapping records consumer order separately from original schema export indices.
  Detection/segmentation keep all schema name slots and use the existing nine-decimal
  conversion. Nonidentity EXIF rotation is rejected to avoid trainer/label disagreement.
- `manifest.json` binds snapshot/schema hashes, original names, saved revisions, assignments,
  exclusions and per-file hashes. `data.local.yaml` is a derived client-path helper, not
  part of portable content hashes; `prepare_dataset.py` regenerates it after a move.
- ZIP cache is derived storage, not a released dataset store. Missing cache after restore
  yields a clear error and requires a new export. A new Prepare captures newer edits.

## Verification (2026-10-06)

Follow-up 2026-10-07: fixed Browse parent folder modal focus. Export hides while
the modal picker is active; deferred reopening lets ImGui close the previous popup.
Both selection and Cancel restore Export without losing prepared data or settings.
Rendered callback smoke passed for both paths and subsequent dataset publication;
full suite rerun: **191 passed**. Physical mouse acceptance remains pending.

- Full suite: **191 passed**. After the final verified-empty allocation/helper changes,
  focused export suite: **15 passed**. Existing Starlette TestClient/HTTPX warning remains.
- Independent expected rectangle/polygon values, raw image hashes, classification layout,
  deterministic repeat ZIP hashes, groups, exclusions/empty files, invalid percentages,
  frozen revisions during later edits, permission changes/idempotency, source corruption,
  failed publication, archive traversal/checksum refusal, no-overwrite destination and
  regenerated local YAML after moving a Unicode-path dataset.
- Real HTTP/rendered desktop smoke: prepared a working export, displayed actual counts,
  downloaded it and published a verified local dataset. `verification-artifacts/phase8`
  contains the screenshot and JSON report. Physical folder-picker/mouse acceptance is
  still for the user; the smoke invokes controller callbacks in the rendered application.
- Offline wheel install outside checkout: migrations, module packaging, desktop render,
  split and format preview checks passed. This is not Nuitka or clean-machine acceptance.
- Ruff lint/format and mypy checked; contract snapshot: `contracts/phase8-openapi.json`.

Not performed: an actual Ultralytics training run (no runtime added), large factory batch,
company LAN/SMB, hard power-loss or disk-full operator drills. These are recorded as
P8-01–P8-14 in `../summary_remain_test.md`. Prior reviewed-release gates remain open.

Format references checked 2026-10-06:
- https://docs.ultralytics.com/datasets/detect/
- https://docs.ultralytics.com/datasets/segment/
- https://docs.ultralytics.com/datasets/classify/

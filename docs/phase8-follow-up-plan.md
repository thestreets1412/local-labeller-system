# Phase 8 follow-up — export diagnostics and project management

Authorized 2026-10-07: collect the discussion into a plan and begin implementation.
This extends `phase8-plan.md`; it does not close earlier phase gates.

## Evidence and user problem

At the company, the user imported images and same-stem YOLO predictions, corrected
rectangles, and could not export one image: `UNREPRESENTABLE_GEOMETRY` after
nine-decimal conversion. They could not identify the source and resorted to
deleting images and recreating projects. Class indices/names also differed from
an existing model. They request project management, data versions, and a hierarchy
such as Factory 1 / Machine A / Detect Top Assy and Detect Side Assy.

Code inspection found that working export omitted `image_id` when calling
`yolo_labels`; job persistence and the desktop both discarded error details.
Conversion stops at the first invalid shape. Shape IDs are UUIDs, not filenames;
SHA256 identifies file content and is not reversible encryption.

A valid source rectangle can fail conversion: for width 3, x1=0, x2=2,
cx=0.333333333 and w=0.666666667 yield left=-0.0000000005. The company image's
actual cause is not yet proven. Existing format tests explicitly reject this
case. Do not instruct users to alter valid source geometry to hide rounding.

## Ordered increments and exit gates

| ID | Requirements | Work and rationale | Exit gate |
|---|---|---|---|
| P8-A | PR14, PR16 | Persist and display aggregate geometry diagnostics across all images/shapes of the saved export snapshot; preserve names and exact decimal values | Multiple failing images/boxes reported, Unicode/duplicate names distinguishable by IDs, no partial publication, report survives job reload, UI exposes details |
| P8-B | PR05, PR16 | Open reported image/select shape using normal claim/dirty-navigation flow; save JSON/CSV; retrieve earlier reports; prepare fresh snapshot after fixes | Fix/save/revalidate succeeds; stale snapshot/revision identified; permission and dirty-state checks retained |
| P8-C | PR16 | Define bounded nine-decimal rectangle representation for valid edge-touching boxes; keep true collapse/invalid source errors | Independent inverse bounds/error tests on all edges, tiny boxes and dimensions; new format version and exact-byte fixtures; old artifact bytes unchanged |
| P8-D | PR02, PR03, PR16 | Class mapping preview before prediction import/export, local model data.yaml comparison, reusable class templates | Swapped/missing/duplicate indices visible before mutation; explicit mapping snapshot; unknown classes rejected; no model execution |
| P8-E | PR01, PR02, PR12 | Project Manager: create/rename/description/search, archive/restore, persistent folders and move projects | Service-only mutations, migration preserves existing data, authorization/revision/audit/idempotency tests, folder-cycle and cross-project checks |
| P8-F | PR02, PR12, PR13, PR16 | Working/schema/export history views and deliberate annotation remapping with preview | Historical identities preserved, remapping creates revisions and uses leases/conflict checks, no fabricated approved release |

P8-A through P8-F are implemented as runnable local increments (evidence below).
Physical mouse/DPI, factory datasets and company acceptance remain open.
Within P8-E, templates and mapping
support precede convenience features. Production hard deletion is not part of
this increment: Archive/Restore is the primary removal flow; permanent deletion
requires a separately specified reference/retention policy.

## Diagnostics contract

- Inspect all geometry in a frozen saved snapshot before split/publication. Errors
  block the whole export; incomplete/unlabeled exclusions remain separate.
- Record project/job/snapshot identity, original filename, image UUID, annotation
  revision/hash, shape UUID and ordinal, class UUID/name/index, raster size, source
  geometry, normalized rounded values, reconstructed edges and failed checks.
- Store exact decimal diagnostics as strings: canonical JSON currently rounds
  numeric values to six places, which would erase a nine-place rounding failure.
- Persist structured details in the failed job and show a readable final report.
  A successful retry uses a new snapshot; an idempotent retry of the old job must
  never pretend to validate later edits. Old jobs without details remain readable.
- Distinguish per-image validation errors from interruption/storage/system errors;
  do not swallow shutdown or falsely claim a full scan after a fatal interruption.
- Keep UI responsive for large reports; full report remains available even if the
  visible preview is capped. Report files must not overwrite existing files.

## Class identity and grouping decisions

Renaming a class, changing a model's output mapping, and correcting mislabeled
annotations are different operations. Never swap class names as a substitute for
correcting imported semantics. Existing `class_id` and schema `export_index`
identities remain stable. A model-facing export mapping must be a separate,
versioned artifact (PR02/PR16 scope extension); prediction remapping creates new
annotation revisions and must distinguish already-corrected labels.

Folder hierarchy organizes projects only. It does not change image `group_key`,
asset equivalence or train/validation/test boundaries. Leaf projects retain their
own task type, schema and permissions. Folder placement must not grant access.

## Version display

- Working data: mutable saved heads, image counts and last modification.
- Class schema: immutable schema ID/version/hash.
- Export snapshot: frozen inputs, timestamp, source revisions and fingerprint;
  explicitly **Unreviewed**, with seed/ratios/mapping and resulting job state.
- Approved release: shown only when actual revision-bound review/release gates
  exist and pass. A project revision or export count is not a dataset release.

## Verification and remaining acceptance

Use synthetic data only. Cover independent expected decimals, multiple shapes,
multiple images, duplicate/Unicode filenames, segmentation, verified empty,
classification regression, persisted job details, new-snapshot retry, UI detail
propagation and no archive on failure. Test existing format bytes unchanged in
P8-A. Local checks do not replace company image reproduction, physical mouse/DPI
acceptance, LAN/SMB, reviewed release gates or production packaging.

Initial baseline: `tests/test_formats.py` — 37 passed (2026-10-07), existing
Starlette/HTTPX deprecation warning. Implementation evidence follows below.

## P8-A implementation evidence — 2026-10-07

Implemented on `codex/phase8-export-diagnostics`:

- Optional aggregate mode in `yolo_labels` reports every unrepresentable shape;
  default behavior and successful serialized bytes/format version stay unchanged.
- Working export validates included geometry before splitting/archive creation.
  Failed job `error.details` contains all issues and frozen provenance; the
  desktop preserves these details instead of rebuilding a message-only exception.
- The panel shows image/shape/class/revision, failed checks and exact values.
  Its preview is capped at 200 errors; a new JSON file in the selected parent
  folder contains the full report. This implements the JSON-saving part of P8-B.
- Retry after failure creates a new request/snapshot. Old failed job reports remain
  persisted and available through the authorized jobs API, including after fixes.

Verification: **196 tests passed**, including 5 new cases; focused formats/export/UI
suite **57 passed**. Ruff lint/format, mypy and diff whitespace checks passed.
Real HTTP/rendered Dear PyGui smoke passed through import, saved invalid-to-export
rectangles, failed job, both shape IDs/names in the panel, disabled dataset save
and successful local JSON report writing. The screenshot was visually inspected.
Local evidence is outside tracked source:
`D:/Python/visionlabel-verification/phase8-diagnostics/desktop-smoke.json` and
`yolo-export-errors.png`. Existing Starlette/HTTPX warning remains.

Remaining limitations: this aggregate pass covers geometry in included, validated
saved annotations. Earlier corrupt/missing annotation or schema failures and later
asset/storage errors still fail immediately; they do not claim a completed geometry
scan. Open-image/select-shape, CSV and desktop browsing of historical failed jobs
remain P8-B. Quantization policy remains P8-C: valid edge-touching source boxes may
still block export, now with actionable diagnostics. P8-D/E/F and all company/manual
acceptance remain open. No dependencies, database migration or historical files changed.

## P8-B implementation — 2026-10-07

- Export errors have numbered entries. Choose an error number and use **Open
  image / select shape** to load the current server image and focus the shape UUID.
  Navigation uses the existing dirty/save guard, claim acquisition and recovery
  handling. No annotation is changed merely by inspecting a report.
- Compare the loaded revision and annotation hash with the frozen report. A stale
  report, removed shape, recovery draft or unavailable editing lease produces an
  explicit status. A report from another project/connection cannot navigate.
- **Previous failures**, **Older** and **Load selected report** retrieve durable
  failed export jobs, newest first in pages of 50. The new read-only
  `GET /projects/{id}/export-failures` uses project authorization and scoped cursors;
  existing `/jobs/{id}` rechecks access when loading details. Old message-only
  failures are readable. History does not become a prepared downloadable dataset.
- Select JSON or CSV and save to the parent folder. CSV retains Unicode via UTF-8
  BOM, nests exact geometry as JSON strings and quotes formula-like user text with
  an apostrophe for spreadsheet safety. JSON retains the exact original strings.
  All saves create a new file, with no overwrite. Full reports are saved even when
  the on-screen preview is limited to 200 errors.
- Existing **Prepare export / retry** remains the fresh-snapshot revalidation step
  after inspecting and saving. Schema/review/release/quantization policies are unchanged.

Verification: real HTTP/rendered desktop smoke passed report -> shape selection
with lease -> edit/save -> historical report reload -> stale-revision warning ->
successful fresh export, plus CSV output. Unit tests cover removed shapes,
recovery/read-only states and guard deferral; API tests cover pagination, scoped
cursors, isolation from another project and nonmember denial (404), then viewer
access after membership is granted. New OpenAPI snapshot:
`contracts/phase8-report-navigation-openapi.json`.

Local rendered evidence: `D:/Python/visionlabel-verification/phase8-report-navigation/`.
Final full suite: **202 passed**; Ruff lint/format and mypy passed. Existing
Starlette/HTTPX deprecation warning remains. Smoke initially assumed source shape
order instead of canonical UUID order; corrected the expectation to the report's
selected shape ID. Nonmember API tests expect the established privacy-preserving
404 response. Both corrected checks and the final full suite passed.
Physical mouse/DPI/company acceptance remains pending. The dialog scrolls on small
viewports. Earlier P8-A limitations for corrupt blobs and fatal storage errors still
apply. P8-C (quantization) is next; P8-D/E/F remain implementation work.

## P8-C/D/E/F implementation — 2026-10-08

User authorization: implement all four remaining increments; resumed after a usage
limit interruption. Earlier evidence above describes the state at each increment,
not the current implementation status.

### P8-C: bounded rectangle quantization

`vl-formats-2` keeps nine-place half-even centers and initially rounded sizes. For
each axis, size becomes `min(size, 2*center, 2*(1-center))`. Source geometry is
validated first; positive sizes and exact reconstructed bounds are checked after
conversion. Only a rounding overshoot can shrink a valid source box; each size
changes by at most one 1e-9 quantum. Reconstructed edge error is bounded by
1.25e-9 times the raster dimension (the tests use this conservative bound).
Zero-size collapse still fails and produces the existing detailed report.

For the 3x3 edge fixture, the exact bytes are:
`2 0.333333333 0.333333333 0.666666666 0.666666666\n`.
Source coordinates and six-place annotation serialization are unchanged.
New working jobs capture the format version; old snapshots without this field
continue using `vl-formats-1`. Cached old exports are never rewritten. Tests retain
explicit legacy rejection and diagnostics alongside independent inverse bounds
for all image edges, fractional geometry and widths through 40 million pixels.

### P8-D: model mapping and templates

- Import and Export dialogs can read a client-local `data.yaml` names list/map.
  The reader is data-only, limited to JSON and common YAML names syntax, with no
  YAML execution, external file includes or network access. Duplicate indices,
  duplicate names, missing slots and unsupported constructs are rejected. Inline
  YAML with escaped single quotes must use an indented block instead.
- The visible `index=project class name` mapping is editable before import/export;
  unknown project classes are rejected. Export requires a complete permutation of
  every schema class. It freezes class-ID-to-model-index mapping in the job and
  writes both schema and model index provenance in `class_mapping.json`.
- Classification consumers still order only observed folders. Its mapping records
  `schema_export_index`, `model_export_index` when overridden, and `consumer_order`
  separately; the UI explains that these can differ for absent classes.
- Class templates persist through the service, are private to their creator, and
  copy active class names in schema-index order plus task type. A new project from
  a template gets new project/class identities and no images. JSON-array input
  preserves class names containing commas. Template creation is audited/idempotent.
- The annotation sidebar displays actual zero-based schema export indices;
  keyboard positions retain their existing shortcut behavior.

### P8-E: project organization

Project Manager provides search, a folder tree, creation, rename, description,
folder placement, Archive/Restore, class inspection and templates. Folder create,
rename/move and deletion of empty folders persist on the server. Cycles and deletion
of folders containing projects (including archived projects) or children are rejected.
Folders are owned by their creator; administrators can manage all folders. Other
users see their own folders and ancestor paths of projects they can access. Folder
placement never grants membership or changes image split `group_key`/asset grouping.

Migration `0004` only adds organization metadata/tables/indexes. Existing project,
class, image and revision identities and immutable bytes remain unchanged. Metadata
updates require maintainer permission, expected revisions and idempotency, and
write audit events in the transaction. Archived projects remain readable through
history, disappear from the normal project list, and reject canonical writes.
Project Manager can show and restore them. Permanent project deletion is outside
the agreed scope; archive is the removal operation.

### P8-F: versions and deliberate remap

The Versions tab distinguishes mutable saved working data, immutable class schema
identity/hash, and unreviewed export snapshots with timestamp, state, source hash,
schema, format, ratios/seed and mapping. It explicitly states that reviewed releases
are not implemented. This does not complete the earlier PR10/PR13 release gates or
the general Phase 3 class-schema migration/editor work.

Remap supports explicitly selected images (filename picker/search or supplied IDs)
and source-name-to-destination-name mappings. Preview shows image names, counts,
source revision/hash and before/after labels. It never changes annotations. Apply
reconstructs from the preview's immutable source, uses normal editing leases/fencing,
checks content/state revisions/schema and maintainer permission again at commit,
publishes new immutable revisions and audits the mapping/source hash. Shape IDs and
geometry remain unchanged. Unknown/deactivated target classes and cross-project
image selections are refused. Remap requests use a separate idempotency scope.

Batch remap commits per image, not as an all-or-nothing transaction. The UI reports
each success/failure and reuses the captured per-image keys for retries in the same
session. After restarting the desktop, inspect saved revisions and select remaining
images before a new preview; do not blindly repeat a swap mapping over an already
changed batch. The editor is locked while manager work runs, even if the window is
closed, to prevent a reload from overwriting concurrent local edits.

### Verification and operational limits

Local synthetic tests cover legacy/new exact conversion behavior, source bounds,
tiny-box refusal, YAML names, export mapping (including classification index
provenance), folder cycles/permissions, archive/restore, metadata conflicts/replay,
template persistence, migration preservation, remap leases/conflicts/idempotency and
unchanged historical annotation/export bytes for detection/segmentation/classification.
The rendered real-HTTP smoke exercises the actual dialogs, hierarchy, metadata,
templates and creation from a template, filename selection, preview/apply remap,
version display, archive/restore and mapped export.

Evidence paths: `D:/Python/visionlabel-verification/phase8-project-tools/` and
`D:/Python/visionlabel-verification/phase8-package/`. The wheel smoke installs offline
outside the checkout and checks packaged migration/desktop/format/split modules.
It is not Nuitka, clean-machine qualification or company LAN/SMB acceptance.

Final verification: **228 tests passed**, including **26 P8-C/D/E/F focused cases**;
Ruff lint/format, mypy (35 source files) and diff whitespace checks passed. The
existing Starlette/HTTPX deprecation warning remains. The phase-2 migration
regression now explicitly checks defaults of the three new project columns before
comparing every historical field and immutable artifact byte. The current contract
snapshot is `contracts/phase8-project-tools-openapi.json`.

Remaining local limitations: restricted YAML syntax is documented above; history
and remap preview are intended for manageable batches, not validated against large
factory archives. Remap accepts at most 500 explicit image IDs per preview. Full
schema editing/reviewed releases, permanent deletion and earlier phase gaps remain
in their original plans. Back up the service before upgrading valuable data to
migration `0004`; use the documented verified backup/restore workflow.

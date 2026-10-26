# Phase 10 — editable classes, responsive review and dataset checkpoints

Planned 2026-10-26; implementation authorized after plan review and resumed
2026-10-27. **P10-A through P10-F implementation is authorized.**
Requested outcome: revise unnecessary classes, improve Accept [S], and save named
dataset versions with messages that can be inspected, exported and restored.
Planning baseline inspected at `c320b5e`. Implementation evidence and design
clarifications are recorded below. Existing Phase 2–6/company acceptance gaps stay open.

## Findings from the current implementation

| Pain point | Evidence | Implication |
| --- | --- | --- |
| Classes cannot be edited in Project Manager | `project_ui.py:ProjectPanel.build` makes `pm_classes` read-only. Templates copy names into a new project; remap changes annotations to existing classes. Phase 3 still lists schema editing as pending. | Add a real schema editor; templates and export index mapping do not solve class lifecycle management. |
| Accept feels slow | `review_ui.py:ReviewPanel.decide` switches an edit claim to review through release/acquire requests, posts review, refreshes overview, populates rows and calls `open_image` even without advancing. | Measure the complete interaction; there is demonstrable repeated work, but no measured dominant cause for this user's delay yet. |
| Accept reloads the same raster | `desktop.py:Desktop.open_image` retrieves image/head/reviews, decodes cached bytes, converts pixels, replaces the texture and fits the viewport. Its completion refreshes overview again. | Reuse an unchanged displayed raster and viewport after acknowledgement; refresh authoritative state and obtain a valid editing claim separately. |
| Rust already exists | `native/texture` pins PyO3 0.27.2 and implements `rgba_to_float`; `texture.py` provides a Python fallback. | First record whether the installed desktop actually uses this extension. A second Rust wrapper alone is not evidence of a speedup. |
| Versions cannot restore a dataset | `project_tools.py:versions` returns working counts, schema history and export jobs; `approved_releases` is empty. | Introduce a durable dataset checkpoint independent of export jobs. |
| Old bytes exist, but restoring membership is absent | Annotation blobs are immutable. Image removal uses `images.archived`; normal APIs reject removed images, and reimport returns `IMAGE_DELETED`. | Explicit historical access, retention and a controlled restore operation are needed; do not merely change a head pointer. |
| Schema changes affect more than the class list | `working_export.py:prepare_snapshot` requires saved annotation schema IDs to match the captured schema. `review.py:decide` also checks the active schema. | Even a rename needs a defined migration policy and regression checks for review/export. |

The Accept service transaction checks project role, lease/fencing, content and
state revision, annotation hash/schema, self-review policy and content validity;
it writes revision-bound review evidence, updates status and fences the claim.
Accept means **REVIEWED_PASS for this saved annotation**, not a dataset release
or a new annotation save. Unsaved edits first pass the existing navigation/save
guard. These guarantees must survive performance work.

## User workflow and terminology

1. Create a project, import images, annotate and review as today.
2. Choose **Create checkpoint**, enter **Version label** (for example `v1.0`)
   and **Message** (`Baseline: seven classes`), inspect counts, then create it.
3. Export **that checkpoint** for training, with its ID/hash in the output.
4. Import more images or change labels/classes; create `v1.1` with a new message.
5. Inspect/diff/export `v1.0` at any time without changing current working data.
6. Choose **Restore to working data** only when old data should become editable
   again. Preview changes, preserve a safety checkpoint and create a new restore
   event. `v1.1` and all later history remain available.

Use an immutable internal checkpoint ID, a project-local monotonically increasing
sequence, a unique version label, nonempty message, actor and server timestamp.
Version labels are user labels, not executable Git refs or required SemVer.
Labels/messages support Unicode and are immutable in v1; no retagging, deletion,
branching, merging, rebasing or force-reset. Validate lengths, whitespace and
uniqueness centrally; never use user labels directly as filesystem paths.

History is linear by creation order. Each checkpoint records its previous
checkpoint ID; a restore additionally records `restored_from_checkpoint_id`.
After restoring v1 while v2 exists, the new event follows v2 and cites v1 as its
source. Content hashes may repeat; event IDs and provenance remain distinct.
Label text is excluded from the content fingerprint so equal data can be compared.

These are **working dataset checkpoints**, with `approved_release=false` even
when all captured images are PASS. Show actual PASS/NG/pending/unlabeled counts.
They do not complete PR10/PR13 approved-release or Phase 4 canonical split gates.

## P10 requirements and planned increments

| Increment | Requirement mapping | Deliverable and exit gate |
| --- | --- | --- |
| P10-A — establish baseline | PR05, PR10, PR18 | Stage timings, installed native status and repeatable synthetic Accept workloads; identify measured bottlenecks before selecting Rust work. |
| P10-B — responsive Accept | PR05, PR09, PR10 | Acknowledged review updates current state without unnecessary raster reload; safe auto-advance and queue refresh. Compare timings to A and pass conflict/retry/permission tests. |
| P10-C — checkpoint foundation and export | PR12, PR13, PR14, PR16 | Durable full-project manifest, named checkpoints/messages, paginated history, read-only image/annotation browser, semantic diff and export from a selected checkpoint. v1 remains exportable after imports/edits/removals. |
| P10-D — editable class schemas | PR02, PR03, PR10, PR12, PR16 | Add/rename/deactivate/reactivate and explicit remap/remove operations with impact preview, safety checkpoint, immutable schema versions and consistent migrated annotation heads. No historical reinterpretation. |
| P10-E — restore a dataset | PR02, PR09, PR10, PR12, PR13 | Restore exact image membership, class configuration and annotation content as new working revisions, preserving later history. Atomic visibility, conflict handling and restart recovery proven. |
| P10-F — workflow and delivery | PR05, PR12, PR13, PR16, PR18 | Full nine-step user journey, failure/recovery and performance evidence, documentation and offline application/native wheel smoke. |

Order: A → B → C → D → E → F. Checkpoints precede destructive class cleanup so
the first bulk change already has a usable recovery point. Each increment remains
runnable. C and D include frozen-schema export support, not just a history UI.

## Accept performance design

- Instrument click/keypress → visible pending state → durable server response →
  interactive current/next image. Record dirty-save, claim release/acquire, network,
  DB wait/commit, blob verification/validation, overview/list updates, cache read,
  decode, conversion and texture upload separately. No confidential filenames or
  label content in performance logs. Do not add times from overlapping work.
- Compare reviewer vs maintainer, clean vs dirty, auto-advance on/off, native vs
  fallback, cold vs warm cache, 640×640 and larger synthetic images, seven and dense
  rectangles, segmentation and classification. Use 100/1,000/5,400-image projects;
  record hardware/storage, versions and sample counts, and p50/p95 over at least
  100 decisions per principal warm scenario. Cold measurements are separate.
- For a clean current image, patch acknowledged review state and preserve texture,
  zoom, pan and selection if asset/content identity is unchanged. An expired review
  claim must never authorize editing: show read-only/pending state until a fresh
  edit claim and current head are checked. Changed content reloads normally.
- Coalesce duplicate overview refreshes and update affected rows. Any aggregate
  cache must reconcile other clients' changes through a server revision/generation;
  do not assume the local +1 is authoritative forever. Suppress stale callbacks
  across project/image switches. Preserve pending-queue pinning and resume order.
- Auto-advance runs once after acknowledged success. Optional bounded raster
  prefetch may use asset hash keys; it must not pre-claim or accept unseen images.
  Failed/retried requests retain idempotency; ambiguous timeouts cannot duplicate
  decisions or advance twice. S key repeat remains latched.
- Consider a transactional claim-mode transition only if measured round-trip cost
  justifies it; it requires explicit owner/token/generation and permission checks.
  Never bypass leases, revalidation, audit, durable commits or self-review policy.
- Port only a remaining measured CPU kernel (for example expensive geometry
  validation) into the existing optional native wheel. Preserve exact outputs,
  rounding, hashes, errors and Python fallback. Compare end-to-end times including
  boundary copies; Rust is optional if workflow fixes remove the bottleneck.
  PyO3's [`Python::detach`](https://pyo3.rs/v0.27.2/parallelism.html) permits Python
  work while a Rust kernel runs; Dear PyGui operations stay on the UI thread.
- Proposed local UX targets, **not measured results**: pending feedback within
  100 ms; warm clean same-image Accept p95 ≤300 ms; warm 640×640 auto-advance p95
  ≤500 ms. Record baseline and final results on the same machine. Missed targets
  require a documented cause/revised gate, not a claim of completion. Dirty saves,
  large images and actual LAN/HDD acceptance have separately reported budgets.

## Checkpoint contents, capture and export

Capture **all current project images**, independent of visible filters, selection
or export eligibility, including unlabeled, NG and verified-empty images. The
manifest pins membership and order, image IDs, original filenames, raw asset
hashes/dimensions, group/asset-equivalence metadata, annotation revision/hash or
explicit absence, schema ID/hash with stable class identities and active flags,
and review evidence bound to the captured revision/hash/schema/state revision.
Preserve task type and schema serialization versions. UI preferences, accounts,
memberships, credentials, source import paths and project-folder placement are
outside dataset content and must not be rolled back.

Only saved server state can be captured. The initiating desktop must Save and
wait, Cancel, or explicitly proceed with saved state while retaining a local
draft; never imply another client's unsaved edits were captured. Display counts
and fingerprint from the actual frozen candidate, not a later live query.

Capture a coherent DB snapshot and durable candidate record, pin its referenced
immutable blobs, then validate hashes and publish a versioned canonical manifest
before committing the checkpoint pointer/audit/idempotency result. Work after
capture may continue but cannot enter that checkpoint. Serialize checkpoint
sequence/parent publication; check authorization again at commit. Freeze manifest
bytes with golden fixtures. Include candidate expiry, retry and orphan cleanup
rules; incomplete or corrupt captures are not selectable completed checkpoints.

Deduplicate raw bytes through existing managed storage. Checkpoints and pending
operations are retention roots: deletion/archive and future garbage collection
cannot remove their images, schemas or annotations. Extend backup/restore
verification to manifests, references, job state and historical blobs. Do not
advertise old export jobs as full checkpoints; any legacy conversion must prove
complete membership/provenance or remain read-only export history.
Existing annotation revisions alone cannot reconstruct arbitrary past project
membership. Start with an explicit baseline checkpoint after upgrade; do not
promise retroactive named versions for moments never captured.

History shows label/message/date/author, image/object counts and review summary.
Read-only browsing resolves pinned blobs through authorized service endpoints,
including images removed from the working project. Semantic diff reports added/
removed images, changed geometry/labels/verified-empty state, class changes and
review-only changes separately; compare stable IDs and content, not only revision
numbers. Preview must support detection, segmentation and classification.

Export gets an explicit source selector: **Current saved working data** or a
named checkpoint. For a checkpoint, resolve no live annotation/schema/group heads.
Freeze mapping, split seed/ratios, inclusion policy and serializer/converter version
in the export job; bind incomplete-review confirmation to that exact source and
options. Preserve existing diagnostics, grouped/duplicate-asset split boundaries
and local download verification. Report all exclusions rather than equating export
image count with checkpoint membership. Provenance includes checkpoint ID/label,
manifest hash and source revisions, plus the existing unreviewed designation.
Repeated identical source/options/converter must reproduce output bytes; changes
of converter version must be explicit and never rewrite cached historical output.

## Class editing and cleanup policy

- Add **Edit classes** in Project Manager. Show active/inactive classes, stable ID,
  name, usage counts and model-facing mapping. Add/rename/deactivate/reactivate
  creates a new immutable schema. Rename preserves class ID; a genuinely new class
  gets a new ID. Never reuse IDs or existing schema export indices.
- Deactivate means no future selection; it does not silently delete annotations.
  If current annotations reference the class, block activation of the proposed
  schema until the user explicitly chooses **Map to another class** or **Remove
  annotations of this class** for those references. Preview affected images,
  boxes/polygons/image labels and lost reviews before applying. Allow a separate
  explicit cleanup action without deactivation. Old checkpoints remain unchanged.
- Removing the last box/polygon leaves an incomplete annotation unless the user
  explicitly verifies an empty image. Removing a classification label produces an
  unlabeled/incomplete image, never an automatic negative or approval. Reactivation
  does not automatically resurrect removed annotations.
- Preserve stable schema indices; build a separate frozen, contiguous model index
  mapping over the chosen schema's active classes. Update the current complete-
  permutation UI/API rules accordingly. A stale or incompatible imported model
  mapping requires an explicit preview/remap. Older checkpoints export their old
  names and mappings. Classification consumer ordering remains explicit.
- To satisfy existing schema checks, migrate every saved working annotation to a
  new revision under the new schema, even for a rename with unchanged geometry.
  Historical bytes and shape IDs are retained. In v1 these new schema-bound heads
  require fresh review; preview this cost. Reusing prior review automatically is
  outside scope. No remaining inactive-class references may be silently dropped
  during export. Templates remain copies, not a live link to project schemas.
- Use the atomic operation mechanism below for schema activation plus head updates;
  do not reuse the existing per-image partial remap loop for a project-wide schema
  switch. Maintainer role is required, including for system administrators.

## Restore and atomic mutation design

Read-only browse/export requires no restore. Restore is a maintainer operation
with an explicit diff and safety checkpoint of current saved data. It restores
the selected checkpoint's image membership/order/group metadata, schema and
annotation content, retaining shared assets and all intervening checkpoints.
Later-added images become absent from working membership; earlier-removed images
return with their original IDs. Neither operation deletes files or import sources.

Restored saved annotations receive **new monotonically increasing revisions**
and provenance pointing at the source revision; never decrement counters or copy
historical JSON while pretending it has a new embedded revision. Restore of an
unlabeled source needs a defined new empty revision/state or append-only absence
event, with no reset to revision zero. Restored review records remain historical:
they do not become new PASS decisions. Restored heads need review again, while
direct export of the original checkpoint retains its captured review evidence.
Preview this distinction; restoring content does not restore accounts or authority.

The proposed `dataset_generation` is separate from metadata `project_revision`:
existing metadata counters alone do not cover every save/review/import. Increment
it transactionally on every dataset-affecting write, including import, save,
review, removal, group/schema changes and restore. Inventory and test all write
paths before relying on it. Bind preview/apply to a generation and scoped token.

For both schema migration and restore:

1. Prepare a durable job from a frozen preview; verify every required immutable
   source and stage new schema/annotation files without changing visible heads.
2. After resolving dirty edits, release the initiating client's own claims through
   the normal API. Reject other conflicting active claims or ask their owners to
   finish; do not steal them. Introduce a persisted project mutation fence covering normal writes and
   claim acquisition during finalization. Recheck generation, claims, permissions
   and source hashes; intervening writes require a fresh preview.
3. Publish immutable files durably, then commit membership/schema/head changes,
   incremented revisions/generations, audit, completed result and idempotency in
   one DB transaction. Create the safety checkpoint before changing working data;
   if its source no longer matches, abort/reprepare. Do not expose a mixed dataset
   through per-image commits. Keep SQL work bounded and measure lock duration.
4. Crash/cancel before commit leaves old working data intact. Crash after commit
   replays the same successful result. Staged files are retained/pinned until a
   deterministic recovery/cleanup decision. Persist fence ownership and recovery
   rules so restart cannot leave a permanent project lock.
5. Other desktops invalidate old heads/claims and reload after the generation
   change. Unsaved drafts remain recoverable but cannot overwrite restored data
   without the normal conflict/explicit reapply flow.

Checkpoint history stays linear and complete. No partial restore or silent skip
is allowed if a blob is corrupt/missing. If large-project transaction limits
require a generation-based working-set pointer instead, specify and verify that
storage migration before implementation; partial visibility is not an alternative.

## Scope decisions and compatibility

| Existing scope | Phase 10 proposal | Rationale / remaining destination |
| --- | --- | --- |
| Phase 3 PR02 schema editor/migration | Implement practical working-schema lifecycle in P10-D | User cannot remove unnecessary classes safely; approved-release schema policy remains Phase 3. |
| Phase 3/8 PR12–14 history/diff | Add working checkpoints and restore in P10-C/E | Export-job history does not satisfy the requested workflow; approved releases remain separate. |
| Phase 8 PR16 saved-working exports | Add pinned checkpoint as an explicit source | Repeated training must use a selected historical dataset, not recaptured mutable data. |
| IMG-DELETE-02/03 irreversible UI tombstones | Propose controlled restoration only from an accessible same-project checkpoint | Required to restore the image set. Ordinary reimport still reports `IMAGE_DELETED`; no unrestricted undelete endpoint. Update deletion docs/tests when implemented. |
| Phase 9 PR10 working review | Optimize interaction and preserve review binding; restored/migrated heads require review | Never synthesize approval by restoring bytes or renaming schema. |

These are **authorized working-data** changes, not retrospective claims that pending requirements
are complete. Phase 2 unfinished PR04/PR08/PR09/PR10/PR12/PR18, Phase 3 approved
releases, Phase 4 canonical splits, Phase 5 reviewed export/import integration,
and Phase 6 production/company qualification retain their original exit gates.

## Verification and completion evidence

- Independent full-journey fixture: v1 with known images, classes and boxes; v2
  adds images; v3 removes an unnecessary class and its annotations. Export v1/v2/
  v3, browse and restore v1, restart, then return to v3. Assert exact membership,
  geometry, names, groups and hashes, surviving later history and monotonic heads.
- Exact-byte golden manifests and historical annotation/export preservation;
  Unicode/duplicate filenames, empty projects, absent annotations, verified-empty,
  all three task types, inactive classes and shared assets across projects.
- API authorization including admin without project role, foreign checkpoint IDs,
  stale preview, lost response/idempotency, concurrent save/review/import/claim,
  duplicate labels and rejected self-review. Restore cannot make old review current.
- Crash injection before/after publication and DB commit; no mixed heads, orphan
  recovery and fence cleanup; missing/corrupt blobs block mutation/export. Back up
  v1–v3, restore into an isolated service and repeat browse/export verification.
- Real HTTP/rendered desktop checks for class preview, checkpoint create/diff,
  historical image browsing/export/restore, dirty drafts, S repeat, cancelled
  review, no unintended zoom/pan reset and stale callbacks. Performance report
  compares A/B; physical mouse/DPI and company LAN/HDD checks remain explicit.
- At implementation time run focused meaningful tests, full required regression,
  Ruff/mypy and contract/migration checks. Extend `test_review.py`,
  `test_phase9_desktop.py`, `test_working_export.py`, `test_image_delete.py` and
  add focused checkpoint/schema tests. Record exact commands/results per increment.
- Build/install application and any changed native wheel offline with Python
  3.12.10, update locks/notices if dependencies change, and include requested
  distribution wheels in `rush-wheel/` commits with updated instructions. Do not claim Nuitka/company readiness from local wheel verification.

Planning verification: source tracing and cross-check against Phase 3/8/9,
deletion/navigation documentation and specification PR02/PR12/PR13. No runtime
benchmark, feature test or implementation completion is claimed by this document.


## Implementation record (2026-10-27)

Application 0.1.3 implements P10 working checkpoints, historical inspection/diff/
export, class edits and atomic restore. Project Manager exposes Dataset tools from
Classes/templates and Versions. Each user checkpoint requires a unique label and
message. Restores append history; later checkpoints remain accessible. Schema
migration and restore create an automatic safety checkpoint and require fresh
review. Old immutable annotation and export bytes are retained.

The storage implementation refines the proposed persistent fence: immutable files
are staged first, then dataset-generation checks, active-claim rejection and a
SQLite BEGIN IMMEDIATE transaction serialize the entire canonical mutation against
all writers. A persistent project lock is unnecessary and cannot be stranded by a
crash. Generation triggers cover image membership/metadata, annotation head/state
and active schema changes. Final authorization, cancellation and expiry are checked
again inside the transaction. Failed jobs can retry a saved preview; pending previews
survive restart and expire after 24 hours. No automatic blob garbage collection is
introduced: staged or expired-operation files are retained, and operation/checkpoint
manifests are backup roots. Pre-0008 backups remain readable and migrate on startup.

Accept refreshes current annotation/review/lease state while reusing the raster
when the asset hash is unchanged. No new Rust extension was created. The existing
optional visionlabel_native 0.1.0 display accelerator remains compatible.

Local verification: full regression 328 passed (147.15 seconds), Ruff passed,
mypy passed for 48 source files. Synthetic fault/concurrency tests cover stale
preview, active claims, cancellation, publication/commit crash points, response
replay, missing/corrupt assets, schema/index identity, backup compatibility and
revision-bound review. The rendered real-HTTP journey passes checkpoint creation,
historical raster/annotation browsing, class removal, diff, frozen export and
restore to new revisions with IN_PROGRESS review status. Evidence is recorded in
`docs/verification-artifacts/phase10/` and `docs/contracts/phase10-openapi.json`.

The 100-image warm same-image benchmark (100 samples, seven boxes, 640x640) measured
p50/p95 125.91/140.11 ms with legacy reload simulation, versus 83.37/100.31 ms with
raster reuse. This is local synthetic evidence, not a guarantee for every dataset.
Full cold/dirty/auto-advance and company LAN/HDD performance qualification, physical
mouse/DPI acceptance and production packaging remain open. Earlier approved-release
and company exit gates remain unchanged; this increment does not close the entire
cross-environment Phase 10 acceptance matrix.


Distribution verification: `scripts/install_phase10.py` installed pinned dependencies
from PyPI into a new external Python 3.12.10 environment, verified committed wheel
hashes, installed application 0.1.3/native 0.1.0, and passed pip check. The rendered
Phase 10 HTTP journey also passed using `-I` against installed site-packages.
The packaged migration and notices are present. Final export/GUI compatibility
changes passed 96 focused regression tests; rectangle/export desktop smoke and
Phase 9 review-only/auto-advance/resume/cancel smoke (10 images) also passed.

A further 30-sample warm dirty-image test (2048x2048, seven boxes, native extension
disabled) measured p50/p95 144.36/193.61 ms including save-before-Accept. This checks
Python fallback usability but does not cover cold-load or auto-advance latency.


The 5,400-image warm same-image run completed (100 samples): p50 **202.28 ms**,
p95 **327.79 ms**. This misses the proposed 300 ms warm-clean p95 target and remains
an explicit performance follow-up, not a passed exit gate. Background full-project
review-overview requests measured p50/p95 434.67/500.33 ms; the endpoint reads the
ordered current image/status set and the client still refreshes authoritative
counts. These asynchronous timings overlap interaction timing and must not be
summed or treated as isolated CPU profiles. No unmeasured native rewrite is claimed.
This build is ready for local use/testing with the functional checks above; full
Phase 10 performance and company acceptance remain open.

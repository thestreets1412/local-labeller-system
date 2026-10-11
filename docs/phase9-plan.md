# Phase 9 — High-volume annotation and review

Plan recorded 2026-10-09. The user subsequently authorized implementation of
P9-A through P9-F and resumed the work on 2026-10-10. Status: **implemented;
local automated verification passed**. Physical mouse/DPI and company acceptance remain
open. This does not close the earlier reviewed-release or LAN gates.

The selected method is the recommended review queue with optional auto-advance.
Contact-sheet triage, bulk approval, inference and assignment scheduling are not
part of this increment.

## Intent and confirmed requirements

Make thousands of images comfortable to annotate and review without repetitive
save dialogs, losing the current row, or confusing saved predictions with reviewed
labels. Application text remains English; user data remains Unicode-capable.

| ID | Requirements | User-requested behavior |
|---|---|---|
| P9-A | PR05 | With Autosave enabled, save immediately before image navigation and continue only after success; keep the two-second idle save |
| P9-B | PR04 | Keep the selected image visible in the left list; show `VisionLabel - Annotation workspace: [1/5000]` using the project's image count |
| P9-C | PR09, PR10, PR12, PR18 | Add `REVIEWED_PASS` / `REVIEWED_NG`; only reviewer/maintainer can Accept (`S`) or Reject (`X`), and only from `IN_PROGRESS` |
| P9-D | PR05, PR06, PR07, PR09, PR10, PR12 | Annotator/maintainer can edit all four working states; saving changed reviewed content resets it to `IN_PROGRESS` |
| P9-E | PR10, PR16 | If any project images are not `REVIEWED_PASS`, warn with counts and allow explicit confirmation to continue working export |
| P9-F | PR04, PR09, PR10 | Review-pending/correction queues, optional acknowledged auto-advance and per-user resume |

User clarification in this conversation: export is warning-and-confirm, not
PASS-only. Reviewer is **review-only**; annotator/maintainer perform corrections.
Maintainer is the only project role with the full project workflow capability.

## Existing evidence and scope changes

Inspection baseline: commit `4f5d4a9`.

- `desktop.py:guard` opens `dirty_dialog` for dirty/pending content without
  consulting Autosave; it also rejects navigation while a save is running.
- `save` already retains an idempotent pending request and supports continuation
  after success. Extend this lifecycle rather than adding a second save mechanism.
- `populate_images` recreates selectable rows; navigation and save refreshes do
  not ensure the selected row stays visible. The title is currently static.
- Image refresh loads the filtered list via `client.list_all`; its length cannot
  supply the unfiltered project total when filters are active.
- Current project capabilities allow reviewer edits and system-admin bypasses.
  Review-only permissions must change server authorization, not just buttons.
- Current save eligibility excludes the new review states. Existing save returns
  `IN_PROGRESS`; review evidence and transitions still need implementation.
- The specification's original PR10 path is submit -> `REVIEW_REQUIRED` ->
  `APPROVED`/`REJECTED`, with explicit reopen before editing approved content.

| Requirement | Phase 9 change and rationale | Destination / retained gate |
|---|---|---|
| PR09, PR10 | Working review directly from saved `IN_PROGRESS`; avoid an extra submit action for each imported prediction | P9-C; original released-version review integration remains open in Phases 2–3 |
| PR05, PR10, PR12 | Changed reviewed working content automatically loses active review on successful save; no separate reopen dialog | P9-D; keep historical review evidence and audit |
| PR09, PR18 | Reviewer becomes review-only; maintainer retains all project operations | P9-C; audit all mutation routes, retain system administration boundary below |
| PR10, PR16 | Warn and confirm incomplete review before working export | P9-E; never turn confirmation into approval or satisfy PR13 |
| PR04, PR05 | Navigation autosave and progress/scroll improvements for 5,000-image use | P9-A/B; retain recovery, conflict and unfinished-gesture safeguards |

These changes apply to the working workflow. Do not alias `REVIEWED_PASS` to a
released `APPROVED` version or remove the earlier completion/skip/release gates.
Define a deliberate adapter and verify release requirements before connecting
these decisions to approved releases. Earlier phase gaps and company acceptance
remain open. No existing artifacts or hashes may be rewritten.

## Working states and permissions

| Action | Viewer | Annotator | Reviewer | Maintainer |
|---|---|---|---|---|
| Browse accessible images, status and permitted history | Yes | Yes | Yes | Yes |
| Edit/save any of the four working states | No | Yes | No | Yes |
| Accept/Reject saved `IN_PROGRESS` | No | No | Yes | Yes |
| Import, project settings, memberships, working export | No | No | No | Yes |

System `admin` is distinct from a project role. Implementation follows
"maintainer alone can do everything": require an appropriate project membership
for annotation/review/export even for an admin; retain admin-only account and
server operations. Existing project creators already receive maintainer membership.
An admin without the required project membership retains system/read access but
cannot annotate/review/export there. An existing project maintainer must assign
the required role. No memberships are silently granted or accounts deleted; a
maintainer does not become a server administrator.

Transitions:

- Image import without labels -> `UNLABELED`.
- Prediction import or successful annotation save -> `IN_PROGRESS`.
- Saved, valid `IN_PROGRESS` + Accept -> `REVIEWED_PASS`.
- Saved `IN_PROGRESS` + Reject with reason -> `REVIEWED_NG`.
- Changed `REVIEWED_PASS` or `REVIEWED_NG` + successful save -> `IN_PROGRESS`.
- Opening, selecting, panning, zooming, no-op saving or navigating does not reset
  review. Undoing an unsaved edit back to saved bytes also leaves review intact.

Review targets saved annotation revision/hash and schema identity, never an
unsaved canvas. A locally dirty reviewed image shows `Review will reset on save`;
the canonical state changes atomically with the successful save. Failed saves
retain the local draft and old canonical state. Saving a correction, remapping,
or restoring old content invalidates review consistently; no alternate mutation
path may retain stale PASS. Historical decisions remain visible as superseded.

`IN_PROGRESS` is necessary but not sufficient for Accept: validate task content,
schema and completion. An empty detection/segmentation needs explicit
`verified_empty`; missing labels are not a reviewed negative image. Classification
must have a valid single label. Reject can identify incomplete saved content.

Retain the original default `allow_self_review=false`. A maintainer may enable
the audited solo-project exception with a reason; full permissions do not bypass
this project policy, validation, leases or revision checks. Explain this in the
UI when the maintainer edits and then attempts to Accept their own revision.

## Review integrity and UI contract

- Persist actor, timestamp, decision, rejection reason, image, revision/hash,
  schema and review applicability. State-only review increments state revision
  without producing a new annotation blob or changing content revision.
- Use review claims and fenced generations alongside expected content/state
  revisions. Review and edit claims must be mutually exclusive for an image.
  Recheck role, project availability, schema, lease and counters in the commit
  transaction; reject stale review/edit and role-revocation races.
- Idempotent retries return the same outcome; duplicate clicks cannot create
  duplicate reviews. No optimistic PASS/NG before server acknowledgement.
- Reviewer browsing uses read/review access, never an edit claim. Review-only
  users cannot change labels, verified-empty, remaps or restoration via HTTP.
- Show `Accept [S]` and `Reject [X]` with role/state-aware availability and reasons.
  Keep `Ctrl+S` for save. Bare S/X ignore text entry, dialogs, modifier chords,
  loading, active gestures and key repeats. One press cannot affect two images.
- Reject opens a compact reason interaction; retain the specification's required
  comment. Suggested shortcuts choose a meaningful preset (e.g. `Wrong class`,
  `Missing object`, `Box needs adjustment`); custom text remains possible.
- Include statuses in filters, list badges, counts, history and export summaries.
  Provide text as well as color. No silent migration of old labels to PASS.

## Autosave and navigation contract

With Autosave on, Next/Previous, list selection and other existing guarded
navigation paths flush completed edits immediately, show `Saving...`, and load
the destination only after acknowledgement and a clean current editor. With
Autosave off, retain the existing explicit dirty-navigation choices.

Reuse an in-flight save instead of creating a competing request. Retain one
explicit destination image ID; repeated keys/clicks must not create a queue that
skips multiple unseen images. Recommended policy: first destination wins while
saving/loading; ignore repeats and show busy state. If content changed during
an earlier idle save, flush that newer content before navigation. Bind callbacks
to image/project identity so an old response cannot update a newly loaded image.

On timeout retry the same request key, preserve draft and destination, and stay
on the current image. On validation, lost lease, authorization or revision failure,
stay on the image and show the error/conflict; never silently discard or leave.
An unresolved polygon/drag must finish or cancel first. Error/recovery dialogs
remain legitimate; only the normal save-confirmation popup disappears.

## Position and large-list behavior

- Native title: `VisionLabel - Annotation workspace: [1250/5000]`. Total is all
  active images in the selected project, independent of status/search filters.
  Empty project: `[0/0]`; no image selected: `[0/N]`.
- Define a deterministic project order with an image-ID tie-breaker. Current
  ordinal is the image's 1-based position in that unfiltered order. Obtain total
  and position consistently from the service; do not derive total from a page.
- Under filters, show a separate `Queue: 32/840` and the project position. If the
  current image leaves the filter after review, keep it visible until deliberate
  navigation or acknowledged auto-advance; never jump because rows refreshed.
- After successful loading, scroll just enough to reveal the selected row. Keep
  manual scroll while inspecting the list; do not snap back every frame. Preserve
  context during save/status refresh, DPI changes and list rebuilds.
- Use IDs for row identity; duplicate/Unicode names are valid. Update counts after
  imports/archives/project switches and handle targets that disappeared.
- Validate list rendering at 5,000 synthetic rows. Avoid full rebuilds for every
  state update; consider clipping/virtualization if measurement warrants it.
  Loading/texture prefetch must stay bounded and must not preclaim other images.

## Export warning and frozen snapshot

Confirmed: warn and let the user continue. This is not a PASS-only restriction.
Proposed dialog: `Review is incomplete: 4,200 PASS, 100 NG, 600 IN_PROGRESS,
100 UNLABELED. Export saved working labels anyway?` Buttons: `Cancel` and
`Export anyway`. Distinguish NG (reviewed but rejected) from not-yet-reviewed;
both prevent an "all passed" summary. Show excluded unlabeled/incomplete images
separately from included non-PASS labels. Do not imply confirmation includes
invalid content or previously excluded unlabeled images.

Prepare a frozen candidate containing review decisions/applicability, content
and state revisions/hashes, schema and project-wide counts. Bind confirmation to
that snapshot/options digest before generating/publishing the working export.
Client-only stale counts or a reusable `confirmed=true` flag are insufficient.
A refreshed snapshot requires its own warning/confirmation. Changes after capture
do not change the confirmed immutable inputs; identify the snapshot timestamp.

All-PASS input suppresses only the incomplete-review warning. Manifest still says
`approved_release=false`; review coverage is separate metadata. Preserve existing
geometry diagnostics, split group/asset boundaries, mapping, authorization,
idempotency and destination safeguards. Version new snapshot/manifest contracts
without rewriting historical export artifacts.

## Reviewing methods — selected method and alternatives

| Method | Benefit | Trade-off |
|---|---|---|
| 1. Keep A/D browsing and add explicit S/X decisions | Smallest learning change; no accidental approvals from Next | Still requires a navigation action per reviewed image |
| 2. Review queue + optional advance after decision (recommended) | Review only pending `IN_PROGRESS`; S accepts and advances after success, X records a reason then advances | Requires stable queue, error handling and protection against held-key repeats |
| 3. Thumbnail/contact-sheet triage | Rapid overview of duplicate-looking images and class consistency | Small boxes are hard to judge; extra UI and memory work; do not bulk-approve unseen detail |

Selected session:

1. Reviewer selects `Review pending` (only `IN_PROGRESS`) and resumes from the
   last image ID/order cursor stored per user/project/filter.
2. Check the image; press S for PASS or X plus a quick reason for NG. Optional
   `Advance after review` moves only after the decision is committed. A/D remain
   navigation-only: skipping a difficult image never marks it reviewed.
3. Annotator selects `Needs correction` (`REVIEWED_NG`), sees the reason, corrects
   and saves; it returns to the pending review pool as `IN_PROGRESS`.
4. Maintainer can correct and review subject to the self-review setting. With
   permitted self-review, save dirty edits first, then review exactly the returned
   revision; never use a single UI action to hide an unsuccessful save.
5. Show project counts (`PASS`, `NG`, `Pending`, `Unlabeled`) and remaining queue
   count. Report review coverage `(PASS + NG) / total` separately from pass rate
   `PASS / total`; image position is not a completion percentage.

Method 2 is implemented. Reject reasons, queue/resume and optional auto-advance
do not authorize bulk approval, model inference or a new assignment system.
Contact-sheet triage remains a later option requiring separate selection. No confidence ordering without
actual persisted confidence data. Existing QC can later offer transparent filters.

## Ordered implementation and verification gates

1. **P9-A:** navigation save lifecycle. Test Autosave on/off, timer save already
   running, rapid navigation, edits during save, lost acknowledgement, failure,
   lease expiry, draft recovery, unfinished gestures and clean no-op navigation.
2. **P9-B:** scroll/title/count contract. Test 0/1/5,000 images, filters, duplicate
   names, paging, sort ties, archived/deleted targets, project switch and refresh.
   Manually check A/D/list navigation, large jumps and Windows DPI.
3. **P9-C/D:** domain transitions, migration, permissions, API/client, then review
   buttons/hotkeys/history. Verify independent clients racing review vs save,
   double review, revoked roles, stale claims/revisions, self-review policy,
   persisted decisions after restart and all three annotation task types.
   Test direct HTTP denials, not only hidden controls. Existing database upgrade
   preserves annotation bytes, revisions and IDs with zero inferred approvals.
4. **P9-E:** snapshot-bound warning/confirmation and manifest. Test mixed states,
   all PASS, all NG, invalid/incomplete/verified-empty input, cancellation, direct
   API attempts to bypass confirmation, changed snapshot/options, concurrent
   edits, retries and preserved historical exports.
5. **P9-F:** queue/advance/resume. Test disappearing queue items,
   other reviewers claiming work, end-of-queue, held keys, failed decision,
   rejection reason cancellation and no approval on A/D.

Likely touchpoints: `desktop.py`, `service.py`, `api.py`, `contracts.py`,
`team_ui.py`, `working_export.py`, `export_ui.py`, `project_tools.py`, database
migrations, statistics/history and their focused tests. Keep transitions and
permission policy independent of GUI/HTTP/ORM details. Update API snapshots and
user documentation with each implemented increment.

Exit requires a saved/reloaded full journey: imported prediction -> IN_PROGRESS
-> PASS/NG -> correction -> IN_PROGRESS -> re-review, plus export confirmation
against the same frozen review snapshot. Measure a 5,000-image synthetic session
and record navigation/render/save latency and resource use; do not claim physical
usability from unit tests. Company datasets, actual two-machine/LAN acceptance,
and earlier released-version gates need their own evidence.

## Implementation details and verification

- Migration `0005` adds immutable revision-bound review records, edit/review claim
  modes, project self-review policy and persisted export confirmation candidates.
  Existing annotation serialization and historical bytes remain unchanged.
- `review.py` implements role enforcement, decisions, settings, history and a
  consistently ordered project overview. `review_ui.py` owns review controls,
  reason entry, readable history and queues/resume. The service remains the only
  canonical writer, including single-PC use.
- Working export returns `REVIEW_CONFIRMATION_REQUIRED` (409) with counts, a
  capture time, source digest and user/project-bound candidate token. Confirmation
  captures no new mutable data and validates unchanged options. Identical inputs
  remain byte-reproducible: capture timestamps live in candidate metadata, not the
  deterministic source digest. Working manifest version `working-review-2`
  carries decisions and state revisions separately from `approved_release=false`.
- The desktop retains one navigation continuation and the existing idempotent
  save request. Esc cancels pending navigation while retaining unsaved content.
  Repeated navigation does not queue unseen images. Error/conflict handling remains.
- List rows retain stable handles when IDs are unchanged; selection/status updates
  avoid destroying thousands of controls. Reveal runs after layout. A loaded image
  that leaves its filter stays visible as a pinned row until navigation; it is not
  counted as pending queue work. Project order is `(created_at, image_id)`.
- Resume cursors are DPAPI-protected, scoped to server/user/project/filter/search.
  A missing/completed cursor advances to the next matching project position, then
  wraps to the first matching image. A/D never imply acceptance.
- All review buttons and raw HTTP endpoints enforce the role/state policy. S/X
  are latched across repeats, typing, modal dialogs and modifier chords. Ctrl+S
  retains save behavior. NG reasons are visible beside the image.

### Local evidence (2026-10-10)

- Full pytest suite: **252 passed**, with the existing Starlette/httpx deprecation
  warning. Includes 14 review service cases, 9 desktop navigation/shortcut cases,
  snapshot confirmation tests, migration byte preservation and review backup/restore.
- Ruff lint, relevant source/test/changed-script formatting, mypy (38 source files)
  and `git diff --check` passed. The unrelated existing formatting difference in
  `scripts/build_brand_assets.py` was left unchanged.
- [Real HTTP/rendered desktop regression](verification-artifacts/phase9/desktop-smoke.json)
  passed rectangle, persistence/recovery/autosave, polygon, prediction import,
  export/diagnostics and project tools workflows.
- [5,000-image rendered session](verification-artifacts/phase9/phase9-smoke.json)
  passed bidirectional row reveal, project title under filters, immediate save and
  navigation, PASS/correction/NG history, a separate review-only account, S with
  acknowledged auto-advance, scoped resume and reject cancellation.
  [Import checkpoint](verification-artifacts/phase9/phase9-import.json) records
  5,000 real service imports in batches of 500 (342.83 seconds total). Initial
  load/render took 1.156 seconds; five jump/load/reveal samples took 0.125–0.250
  seconds; save and navigation took 0.156 seconds. Peak process working set,
  including the test server, was 185,917,440 bytes (177.3 MiB).
- The volume fixture uses 16×16 synthetic PNGs. These measurements demonstrate
  list/workflow behavior, not high-resolution factory-image decode performance or
  single-job 5,000-file import throughput. The separate
  [10-image role-aware smoke](verification-artifacts/phase9/phase9-small-smoke.json)
  also passed. Rendered [workspace](verification-artifacts/phase9/phase9-workspace.png)
  and [reviewer](verification-artifacts/phase9/phase9-reviewer.png) evidence is retained.
- [Offline wheel smoke](verification-artifacts/phase9/package-smoke.json) passed
  build, noneditable install outside the repository, packaged migration/desktop
  and split/format CLIs. This is not Nuitka or clean-machine qualification.

Physical mouse/DPI acceptance, high-resolution company data, real two-machine
LAN/SMB operation and earlier reviewed-release gates remain open. Working review
and export do not satisfy approved-release requirements. Restart the service and
desktop to load this increment; normal service startup applies migration `0005`.
A maintainer working alone must explicitly enable self-review in Review settings
with an audit reason before reviewing their own saved annotations.

### Review follow-up (2026-10-11)

The user authorized the fixes in [the project code review](code-review-2026-10-11.md).
Image-loading failures now release acquired claims and retain unresolved claim
handles/keys for cleanup retry. Dirty navigation with an unavailable save offers
draft-preserving recovery choices even with Autosave enabled. Class/delete commands
cancel an unfinished drag before changing content, so mouse release cannot restore
the older annotation snapshot. Export preparation locks the mapping field alongside
its other frozen options. Regression evidence and the related metadata/split fixes
are recorded in that review document; earlier acceptance gates remain open.

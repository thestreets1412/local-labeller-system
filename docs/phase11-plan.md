# Phase 11 — Storage efficiency and retention

Planned 2026-10-28; implementation subsequently authorized by the user and resumed
2026-10-29. **Local implementation and delivery verification recorded 2026-10-30.
No production data cleanup has been performed.** See `phase11-execution.md` for
evidence, deliberate deviations and remaining acceptance gates. This is not a
claim that every company/measurement gate below has been completed.
Baseline: `notification-to-button` @ `9c0e8e4f85e1c10f5607a99b5a88ca3553247e16`.

## Problem and measurable objective

The company dataset has about 5,400 source images, reportedly about 1.5 GB.
The user now reports these directory sizes (display units not yet independently verified):

| Directory | Reported size | Planning consequence |
| --- | ---: | --- |
| `inbox` | 0 KB | Already emptied by the user; inbox automation will not solve this incident. |
| `managed/assets` | 4.63 GB | Inventory hashes and retention references before considering reclamation. |
| `managed/projects` | 19.2 MB | Preserve annotation/checkpoint history; not the primary target. |
| `export-cache` | 13.9 GB | Highest priority: about 74% of the reported total. |
| `db` | 169 MB | Measure categories/WAL; no automatic history purge or VACUUM in this phase. |

Total is approximately 18.7 GB. These are user measurements, not a disk scan by
the agent. They supersede the earlier approximate 10 GB estimate.

Goal: explain every storage category, safely reclaim eligible old export archives,
bound future archive growth, and explain the 4.63 GB of assets while preserving
saved annotations, named checkpoints, historical export provenance and restore.
Success is measured in physical files/bytes and usable workflows, not only UI counts.

Canonical assets are already stored by SHA-256 across projects in one service root.
`managed/assets` contains original image bytes, not rendered thumbnails or copies
made by each checkpoint. Possible explanations for its size include images from
other/archived projects, removed images retained for history, different source
encodings, and unreferenced files after interrupted publication. These are hypotheses.
No plan may label the difference from 1.5 GB as disposable without a reference scan.

Evidence: [storage audit](storage-efficiency-audit.md). Execution checklist:
[Phase 11 implementation plan](superpowers/plans/2026-10-28-storage-efficiency.md).

## Reviewed boundary — one configured root only (2026-10-28)

The user explicitly limits Phase 11 storage management to the configured service
data root. This restriction supersedes the earlier client-cache and offline-GC scope.

- Bind each operation to the service's validated absolute root and root identity;
  display that exact path in the Storage window and every cleanup preview. HTTP
  callers cannot supply a different filesystem root. Offline diagnostics require
  an explicit `--root`; no default AppData fallback for these new commands.
- Inventory, hashing, cleanup, staging, reports and maintenance logs stay within
  this root. Store reports in `<root>/reports/storage/`; metadata/journals in its
  database/managed storage, and ZIP staging in `<root>/export-cache/`. Do not fall
  back to `%TEMP%`, AppData, the working directory or a parent if a path is unavailable.
  Configure new diagnostic SQLite work to avoid external temporary-file spill
  (memory-backed temporary tables or explicitly root-contained staging).
- Never scan other service roots, drive roots, sibling/parent directories, AppData,
  Downloads, external saved datasets or external backup locations. Filesystem free
  space may be queried for the configured root; this does not authorize directory
  enumeration elsewhere. No automatic move of data to another location.
- Resolve and validate containment component-by-component before access. Reject
  traversal, absolute/UNC/drive-relative paths and Windows alternate data streams in
  stored relative paths. Do not follow symlinks, junctions or other reparse points,
  including those inside root; report the entry without opening its target.
  Out-of-root DB/manifest references are integrity errors, never permission to follow.
- A string-prefix comparison is insufficient (`D:\\Data2` is not inside `D:\\Data`).
  Revalidate root identity, path and file identity at apply; use Windows handle-based
  containment/no-reparse protections to prevent a path swap between checking and
  opening/deleting. If containment cannot be established, skip/fail closed.
  Multi-linked files are excluded from mutation rather than trying to inspect other links.
- Bind preview tokens, background jobs and policy generation to root identity.
  Changing/replacing the root invalidates old work. No recursive wildcard deletion
  of root or a category directory. Only registered eligible archive files can be
  deleted individually; contained unknown files and user exports remain report-only.
- Existing user-invoked Save dataset and backup/restore are independent workflows,
  not cleanup actions. Phase 11 will not invoke them, inspect their external
  destinations or add destination scanning. Receipt compatibility can be tested in
  isolated synthetic fixtures without touching the company's external folders.
- Remove global client-cache management from Phase 11. Also defer orphan deletion:
  its original verified-backup prerequisite would inspect a backup outside root
  (the existing backup tool requires that location). P11-D reports orphan candidates
  only; no substitute in-root backup or weakening of restore safeguards.

The repository documentation/source work is distinct from runtime data management.
This boundary describes the new software operations; tests use explicitly designated
synthetic roots and never operate on production storage by default.

## Requirements and increments (revised)

| Increment | Requirements | Deliverable / gate |
| --- | --- | --- |
| P11-A — inventory | STOR-01; PR12/PR18 | Read-only storage report reconciles file bytes with DB/references, attributes shared/history assets without double counting, and explains unknowns. |
| P11-B — reclaim export cache | STOR-02; PR12/PR13/PR16/PR18 | Adopt legacy archives, persist provenance, preview/apply selective archive cleanup, protect pin/build/download, recover interrupted cleanup. |
| P11-C — prevent regrowth | STOR-02/03; PR13/PR16/PR18 | Configurable quota/age, explicit pinning, concurrent-safe reuse of identical frozen exports, disk reservation and visible failure reasons. |
| P11-D — asset reconciliation | STOR-01; PR12/PR13/PR18 | Deep hash inventory inside root and report-only orphan candidates; no asset deletion. |
| P11-E — desktop controls | STOR-01/02; PR05/PR18 | Root-bound Storage window, cleanup preview/results and containment feedback; no AppData/client-cache management. |
| P11-F — acceptance and delivery | PR05/PR12/PR13/PR16/PR18 | Synthetic 5,400-image disk measurements, fault/race tests, checkpoint/export/backup restore drills, docs and installed-wheel smoke. |

Order: A → B → C → D → E → F. B includes a minimal usable admin UI so recovery of
space does not wait for the final polish in E. D can report zero reclaimable bytes;
that is a valid result when all 4.63 GB are required by existing records/history.

## Storage policy decisions

### Export cache, provenance and older installations

- An export job and its evidence are permanent history; its downloadable ZIP has
  a separate availability state. Removing ZIP cache never deletes a checkpoint,
  annotation revision, job audit or saved dataset outside the service root.
- Persist a verified receipt before an archive becomes eligible: original job ID,
  frozen snapshot/hash, manifest, archive hash/bytes, converter/template identity,
  actual split/mapping, review evidence and timestamps. Receipt files are managed
  metadata and must participate in backup/restore.
- For pre-Phase-11 ZIPs, read and verify the archive/manifest against job evidence;
  persist receipts without rewriting the existing ZIP. Legacy provenance that
  cannot be verified is reported as blocked, not guessed or silently discarded.
- First upgrade is **report/adopt only**, with legacy archives protected until the
  administrator selects them in a reviewed cleanup or retention-activation preview. Never delete
  13.9 GB merely because the new version starts.
- Explicit pin protects an archive from automated or manual cache eviction until
  unpinned. Build/download protection is a separate runtime lease. Archive count
  and byte totals distinguish legacy-protected, pinned, busy and eligible files.
- Cleanup preview is server-generated and binds exact artifact IDs, paths,
  hashes/sizes and policy generation, expires after 10 minutes, and requires
  revalidation at apply. Unknown files are reported, never selected by wildcard.
- Apply is idempotent and journaled. Per-file results distinguish deleted,
  skipped-busy, changed-since-preview, protected and failed. Disk/DB races or a
  Windows file-sharing error must not turn a successful historical export job
  into a failed job. Recovery reconciles missing ZIPs with the eviction journal.
- Download acquires protection before verification/open, holds it through response
  completion or disconnect, and releases in a guaranteed response-finalization
  path. Cleanup/build/reuse share the same service-side coordination.

### Proposed defaults after administrator activation

- Total retained export-cache budget: **4 GiB**, including pinned archives.
- Evict eligible unpinned archives unused for **7 days**; when quota pressure
  requires it, evict least recently successfully accessed eligible archives first.
  Either expiry or quota pressure may select a file; not both required.
- Pinned/legacy-protected/in-flight bytes are never forcibly deleted. If these
  prevent meeting the budget, show the overage and block a new materialization
  that cannot fit; suggest unpinning, cleanup or increasing the budget.
- A single archive larger than the budget is not silently exempt. Preview its
  estimated size and require an administrator to increase the budget before build.
- Before building reserve estimated ZIP bytes plus **1 GiB free-space headroom**
  on the configured root's volume, accounting for in-flight reservations.
  Check again while writing and handle ENOSPC without publishing a partial result.
  Client destination disk checks are outside this phase's revised scope.
- Startup (after activation), before new builds, and every 15 minutes while the
  service runs invoke the same bounded retention policy. Activity checks and
  service serialization prevent maintenance from racing active publication.
- Administrators may change budget/age and disable automatic eviction; report the
  consequence. Manual cleanup remains available. Settings and changes are audited.

At 4 GiB (approximately 4.29 decimal GB), reducing 13.9 decimal GB to that budget
would reclaim about **9.6 GB**, **only if enough archives are eligible**. Pins,
legacy protection, activity and unit differences can change this estimate.
This is not a promise that the full workspace will shrink to the 1.5 GB source size.

### Reuse and historical behavior

- Keep idempotency per request, and add per-project artifact reuse keyed by the
  complete frozen snapshot and export recipe: asset/revision/schema/review identities,
  checkpoint provenance, mapping, split options/algorithm, converter version,
  generated-template fingerprint, and archive profile. Prefer conservative misses
  over reuse with different evidence. Do not share authorization across projects.
- Concurrent equivalent requests produce at most one ZIP. Separate request/job
  records may reference the artifact; removal cannot rely on one job alone.
- An unchanged re-prepare reuses an available verified ZIP; altered labels, review,
  schema, membership, checkpoint identity or options require the appropriate new key.
- If a historical ZIP was evicted, retain the old receipt/hash and show
  `Archive removed from cache. Prepare a new export from this snapshot or checkpoint.`
  Re-preparing creates a **new job/result**, using the immutable saved inputs with
  an explicit current converter version. Do not rewrite the old result or promise
  byte-identical regeneration across converter versions. Unsupported snapshots
  give a reason and recovery action. Users needing exact original ZIPs must pin them.
- Approved-release gates remain pending; working checkpoints/exports are not releases.

### Asset investigation — report only

- Quick scan: file count/bytes by type/path, DB-declared unique bytes, active project
  references, archived memberships and other retention reasons; no full raster decoding.
- Deep scan: stream SHA-256, compare filename/DB digest and byte length, report
  byte-identical files with different paths and verify reference targets. No image
  bytes, filenames or class content leave the LAN; export a redacted summary by default.
- Categories are disjoint for totals: active/shared, history-only, registered with
  no explained use, file-only orphan candidate, corrupt/missing/unknown. Additional
  reason tags can overlap. Report project logical bytes separately from physical
  unique bytes. A DB asset row is itself a retention root in Phase 11.
- Retention references include all projects (including archived), image tombstones,
  all annotation revisions, class/checkpoint history, dataset operations (including
  expired/cancelled until explicitly retired), frozen jobs/candidates and receipts.
- Only file-only orphans with **no DB or historical reference**, age at least
  **7 days**, valid containment and a verified deep-scan identity may be proposed.
  Any unreadable reference, unsupported schema or integrity uncertainty blocks GC.
- File-only orphan candidates are report-only in Phase 11. No asset file or asset
  row is deleted, moved or rewritten. A future separately approved maintenance plan
  must address verified backups and its exact filesystem boundary before reclamation.
- When files have the same hash but different paths, retain all referenced paths.
  An unexpected duplicate path is not automatically safe just because a canonical
  path exists. Integrity failures get repair guidance, not automatic deduplication.

## Desktop and permission contract

- **Storage usage** accessible from the current Project Manager window, showing
  the exact configured server root and only its usage. Refresh,
  Inspect assets, Manage export cache, Preview cleanup and Open report show visible
  progress, result or a reason plus next action in the current window.
- Global inventory/policy/apply require service administrator authorization.
  Project maintainers retain current project export permissions; they do not gain
  cross-project names, paths or bytes through the new report. Admin storage access
  does not grant annotation mutation or export-content access without project role.
- No client-cache usage scan, Clear image cache, AppData retention, external temp
  scavenging or external export/backup inspection is added. Temporary files inside
  root are reported; only an active export's own validated staging file follows its
  existing failure-cleanup lifecycle. Unknown/crash-residue files are report-only.
- All UI text is English. Paths, names, messages and data remain Unicode-capable.

## Scope intentionally left outside Phase 11

| Item | Rationale and destination |
| --- | --- |
| STOR-06: global client cache and external temporary cleanup | Outside configured root. Removed from Phase 11 by user boundary clarification; future separately authorized client-cache phase only. |
| File-only orphan deletion | Original prerequisite requires inspecting an external verified backup. Deferred to a separate maintenance plan; P11-D remains read-only and preserves the boundary. |
| STOR-04: preview-only prepare / ZIP streaming | Existing prepare/download contract can remain while retention/reuse solve growth. Revisit after P11-F if peak disk remains a measured problem. |
| STOR-05: inbox auto-removal/direct ingest | Inbox is already zero; requires separate source-ownership/retry design. Future ingestion increment. |
| STOR-07: deleting historical preview/candidate payloads or DB compaction | Current metadata is acceptable; future metadata retention phase with explicit audit policy. |
| STOR-08: shared training asset pool, links, incremental dataset export | Requires training-loader/portability/isolation design; future training-storage phase. Portable outputs remain full copies. |
| Deleting registered history assets/checkpoints, image re-encoding, perceptual dedup | Would change retained evidence or restore guarantees; separate explicit destructive-retention policy if ever requested. |
| Incremental backups or new Rust/PyO3 extension | Not needed to fix this storage lifecycle; retain existing stack and backup tools. |

## Exit gates and rollout

1. Inventory totals reconcile with actual files on a synthetic root, including
   shared assets, Unicode paths, missing/corrupt data and interruption residues.
2. Legacy upgrade retains all existing ZIPs until explicit activation/selection.
   Verified receipts and existing checkpoints survive backup/restore.
3. Repeated prepare of identical frozen input yields one physical archive; changed
   input yields a separate correct result. Auth checks apply on reuse/download.
4. Activated quota bounds idle cache after eligible cleanup; blocked overage is
   visible. Pinned and active files survive cleanup races, disconnect and restart.
5. Asset diagnostics never remove or alter any asset, registered or otherwise.
   v1 → annotate/change classes/import → v2 → cache cleanup → restore/export v1
   still works, with later history preserved and new job provenance explicit.
6. Synthetic 5,400-image workload reports before/after steady and peak bytes on
   each volume, cache hit/miss/eviction counts and timings. Company dataset remains
   untouched until its administrator reviews the generated report and cleanup list.
7. Relevant tests, full regression, lint/type checks, small-window/DPI GUI smoke,
   and wheel installation smoke pass. Update English operator help, SoftwareExplainer,
   wheel version/install commands and distribution artifacts only during implementation.
8. Containment tests instrument file operations to prove no outside-root enumeration,
   open, hash, create, move or delete by Phase 11 management. Include sibling roots,
   prefix collisions, AppData sentinels, poisoned DB references, junction/symlink
   escape and replacement between preview/apply. Outside sentinel contents/mtime and
   directory entries remain unchanged; rejected paths show a reason and next action.

Implementation branch: `codex/phase11-storage-efficiency`. Local implementation and
verification evidence are recorded in `phase11-execution.md` and
`verification-artifacts/phase11/`. Production cleanup, company acceptance, and
commit/push have not been performed. The original exit gates above remain the
acceptance target; see the ledger for explicit measurement/UI limitations.

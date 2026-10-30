# Phase 11 Storage Efficiency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task after implementation is authorized. Steps use checkbox (`- [ ]`) syntax for tracking. This document does not authorize implementation, cleanup, commits or pushes.

**Goal:** Explain and reduce storage growth without losing annotation history or checkpoint restoration.

**Architecture:** Keep the existing global immutable image store. Introduce explicit export artifact lifecycle and durable receipts separate from job history; make storage accounting and retention decisions independent of GUI/HTTP, with mutation coordinated by DataTracking. All Phase 11 management is bound to one configured root; assets are inspected only, never reclaimed in this phase.

**Tech Stack:** Existing Python 3.12.10, Dear PyGui, FastAPI, SQLAlchemy/Alembic and SQLite; Python standard library for filesystem/hash operations. No new runtime dependency or native extension planned.

**Spec:** [Phase 11 specification](../../phase11-plan.md), [source audit](../../storage-efficiency-audit.md), [product specification](../../../VisionLabel_DataTracking_Specification.md).

## Execution status (2026-10-29)

Implementation is on `codex/phase11-storage-efficiency`. The original step checklist
below is retained as the planning baseline, including proposed test filenames.
Actual evidence and deliberate deviations are tracked in
[the execution ledger](../../phase11-execution.md); its task/evidence matrix
supersedes the unchecked planning steps. No production cleanup or push occurred.

## Global Constraints

- All application-authored UI text, menus, buttons, tooltips, validation/error messages, dialogs, and installer text must be English. No Thai localization or language switcher is planned for v1.
- Preserve raw image bytes, original raster coordinates, and the no-auto-EXIF-rotation policy. Keep image-to-screen coordinate conversion centralized.
- The service is the only canonical writer. The desktop must never write SQLite or canonical annotations/assets directly, including in single-user development.
- Use `.\.venv\Scripts\python.exe` for every Python command. Do not rebuild the environment or install globally.
- Retain existing authorization, idempotency, immutable history, review evidence and pending company/release gates.
- Phase 11 defaults: export budget 4 GiB, age 7 days, free-space headroom 1 GiB; automatic retention initially disabled on upgrade. Preview validity 10 minutes. File-only orphan report candidate age 7 days; report only, no orphan apply.
- User scope revision: all storage scans, hashes, reports, staging and cleanup remain under the one validated configured root. No AppData/client-cache, external export/backup destinations, parent/sibling roots or external temp directories. Reports go to `<root>/reports/storage/`; no out-of-root destination option or fallback. Existing independently requested export/backup workflows are not invoked by maintenance.
- Enforce the phase spec's root identity, no-reparse/containment and handle-based race protections before every filesystem operation. Stored references cannot extend authority. Only registered eligible archives may be evicted; no asset deletion, generic temp scavenging or recursive wildcard cleanup.
- Read the spec's scope exclusions: no inbox auto-delete, registered asset/history deletion, re-encoding, training links/pool, automatic metadata purge or DB compaction.
- Use synthetic fixtures only. Before implementation inspect Git status and create/reuse the authorized implementation branch; preserve the existing planning documents. Focused commits/pushes require user authorization covering that work.

## Review Focus

1. Download protection must start before verification/open and end on disconnect as well as success; pin changes during cleanup invalidate selection (Tasks 3–4).
2. ZIP publication, receipt adoption and deletion can each be interrupted between filesystem and DB changes; restart must preserve evidence and reconcile availability (Tasks 2–3).
3. Corrupt/missing/unknown historical manifests and Windows junctions must block definitive orphan classification, not look like absent references (Tasks 1 and 6).
4. Identical images with different labels/review/checkpoint/converter inputs must not cause a wrong export reuse (Task 5).
5. Configured-root changes, poisoned references, prefix collisions and junction replacement must never extend scans/writes/deletes to external paths; AppData and recovery drafts stay untouched (Tasks 1, 3, 6 and 7).

## File and interface map

New modules keep lifecycle policy out of the already large service/desktop files:

| File | Responsibility / public interfaces |
| --- | --- |
| `src/visionlabel/storage_inventory.py` | `scan_storage(root: Path, *, deep: bool = False) -> dict`; JSON-serializable report and complete reference traversal. Offline callers hold DirectoryLock; online service adapter uses a consistent DB view and marks unstable filesystem observations. |
| `src/visionlabel/storage_policy.py` | `select_evictions(artifacts: list[dict], *, max_bytes: int, max_age_days: int, now: str, reserve_bytes: int = 0) -> dict`; pure deterministic selection and blocked-overage accounting. |
| `src/visionlabel/export_cache.py` | `adopt_legacy_exports(srv, actor) -> dict`; `preview_cleanup(srv, actor, artifact_ids: list[str]) -> dict`; `apply_cleanup(srv, actor, token: str, key: str) -> dict`; `acquire_download(srv, actor, job_id: str)` context-managed lease; `artifact_key(snapshot: dict, recipe: dict) -> str`. Owns artifact state, journal and coordination. |
| `src/visionlabel/storage_boundary.py` | `StorageBoundary(root: Path)` validates configured root identity; `inventory_entry(relative: str) -> dict` inspects without following reparse targets, `open_read(relative: str)` and `open_new(relative: str)` return context-managed handles, and `unlink_registered(relative: str, expected_identity: dict) -> None` validates identity/containment through deletion. All paths relative to root; multi-linked mutation rejected. |
| `src/visionlabel/storage_ui.py` | `StoragePanel(app)` with `build()`, `show()`; uses API only for server storage and existing feedback conventions. |

Dictionary shapes are frozen in task tests and API contracts, not arbitrary logging:

- Inventory: `schema_version`, `complete`, `warnings`, `categories` (name/count/bytes),
  `assets` (hash/path/bytes/category/reasons/project_ids), `totals` and `scan_id`.
  Unknown allocated-size values are null, never guessed. Online raced scans cannot authorize GC.
- Artifact input to policy: `id`, `bytes`, `last_access_at`, `state`, `pinned`,
  `legacy_protected`, `in_flight`; UTC timestamps use the existing service format.
- Policy output: `candidate_ids`, `reclaimable_bytes`, `retained_bytes`,
  `blocked_bytes`, `fits_budget`; count shared physical artifacts only once.
- Cleanup preview: `token`, `expires_at`, `entries`, `reclaimable_bytes`, `blocked`.
  Apply result: `deleted_bytes`, `entries` with actual outcomes and `audit_id`.
- Recipe: `format_version`, `split_algorithm`, `archive_profile`, `templates_sha256`.
  `artifact_key` hashes canonical `{snapshot, recipe}`; project and checkpoint provenance
  remain in snapshot. Availability and job/request identity do not enter the key.

## Task 1 / P11-A: Read-only inventory and company diagnostic

**Files:** Create `storage_inventory.py`, `storage_boundary.py`,
`tests/test_storage_inventory.py`, `tests/test_storage_boundary.py`; modify
`src/visionlabel/cli.py`, `src/visionlabel/api.py`, `docs/operations-guide.md`.
Consumes `operations.references`, immutable blob paths and historical snapshots.
Produces `scan_storage` and the report shape above.

- [ ] Add synthetic tests: `test_assets_shared_across_projects_count_once`,
  `test_history_only_assets_retained`, `test_unknown_and_corrupt_refs_block_gc`,
  `test_scan_does_not_follow_junctions`, `test_read_only_scan_does_not_migrate`.
  Add `test_sibling_prefix_is_not_contained`, `test_poisoned_db_reference_not_opened`,
  `test_root_replacement_invalidates_scan`, `test_report_cannot_escape_root` and
  `test_no_temp_or_appdata_fallback`. Track actual file operations, not only report output.
  Assert two project references to one 100-byte file yield 100 physical bytes,
  200 summed project logical bytes, and zero reclaimable registered asset bytes.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_storage_inventory.py -q`;
  confirm expected missing-feature failures before implementation.
- [ ] Implement the inventory with bounded streaming in deep mode; read SQLite
  without `Service(...)` initialization/migrations for offline inspection. Any unknown
  schema or reference parsing failure sets `complete=False` and includes a reason.
- [ ] Implement `StorageBoundary` with the spec's Windows handle-based protections;
  metadata checks reject external references before opening them. Do not resolve/traverse
  a link target for inspection. Route new management file access through this boundary.
- [ ] Add proposed `datatracking storage-report --root ... [--deep]`
  as an offline read-only command that fails clearly if the service is running.
  Require an explicit root, and create an exclusive report name below its
  `reports/storage/` directory; reject redirects and never fall back outside root.
  Add admin-only `GET /api/v1/storage/usage` for live accounting; return aggregate
  categories by default, paginate asset details, and omit paths from redacted reports.
- [ ] Run the tests; expect PASS and an unchanged synthetic root except the explicitly
  requested output report. Document how the company can produce a report locally.

## Task 2 / P11-B1: Artifact registry and durable legacy receipts

**Files:** Create `export_cache.py`, `tests/test_export_cache.py`,
`src/visionlabel/migrations/versions/0009_storage_retention.py`; modify
`src/visionlabel/working_export.py`, `src/visionlabel/operations.py`,
`src/visionlabel/service.py`, `tests/test_operations.py`.
Consumes Task 1 accounting; produces legacy adoption and receipt persistence.

- [ ] Add tests `test_upgrade_keeps_legacy_zip_bytes`, `test_receipt_backup_restore`,
  `test_invalid_legacy_archive_stays_protected`, `test_adoption_restart_is_idempotent`.
  Assert ZIP SHA/path unchanged, automatic retention false, and receipt roundtrip intact.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_export_cache.py tests/test_operations.py -q`;
  confirm the new tests fail for missing registry/adoption support.
- [ ] Create tables: `export_artifacts` (identity/key/path/hash/bytes/receipt pointer,
  availability, pin, legacy protection, access time), `export_job_artifacts`
  (job-to-artifact links), `storage_policy` (singleton configuration/generation),
  `storage_cleanup_operations` (actor/token expiry/selected identities/results).
  Migration creates metadata only; no filesystem deletion or eager hashing in migration.
- [ ] Persist receipts under `managed/export-receipts/<sha>.json` with immutable
  publication before DB pointers. Add their references to backup/verification.
  Adopt existing job ZIPs on explicit admin scan, verifying checksum and manifest;
  interrupted adoption is safely repeatable. Missing ZIPs retain original job result.
- [ ] Register new successful export archives/receipts transactionally. Recovery checks
  publication state without deleting unknown files. Unverifiable legacy archives remain
  protected and display an actionable error.
- [ ] Run the targeted tests; expect PASS. Capture migration/backup evidence in docs.

## Task 3 / P11-B2: Preview/apply cache cleanup with download protection

**Files:** Modify `export_cache.py`, `api.py`, `working_export.py`, `service.py`;
create `storage_ui.py`, `tests/test_storage_cleanup.py`; modify `desktop.py`,
`project_ui.py`, `tests/test_button_feedback.py`.
Produces preview/apply interfaces, response-lifetime leases and minimal Storage UI.

- [ ] Test `test_cleanup_preserves_job_checkpoint_and_receipt`,
  `test_stale_preview_rejected`, `test_cleanup_retry_does_not_double_delete`,
  `test_download_disconnect_releases_protection`, `test_pin_or_download_race_skips_file`,
  `test_restart_between_unlink_and_commit`, `test_nonadmin_storage_forbidden`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_storage_cleanup.py -q`;
  expect missing endpoint/lifecycle failures.
- [ ] Add admin-only `POST /api/v1/storage/export-cache/preview` with artifact IDs,
  `POST /api/v1/storage/export-cache/apply` with preview token and Idempotency-Key,
  and `PATCH /api/v1/storage/export-cache/{artifact_id}` for pin/unpin. Preview
  checks receipts and legacy protection selection; explicit user selection can release
  legacy protection, but never bypass an explicit pin or active lease.
- [ ] Implement journaled ACTIVE → EVICTING → EVICTED transitions with revalidation
  and per-file results. Apply does not delete the job, receipt, or immutable inputs.
  Windows unlink failures are recorded and retriable. Tokens bind actor and policy generation.
  Bind root identity too; require `StorageBoundary.unlink_registered` at apply.
  Add tests for junction replacement after preview, external hard-linked files,
  root switching and preserved external sentinel files.
- [ ] Wrap download response execution so the lease covers checksum verification,
  streaming and disconnect/error finalization. A background callback alone is insufficient
  unless tests prove release on the actual disconnect path. No timeout may evict a live lease.
- [ ] Wire Storage usage / Manage export cache / Preview cleanup / Apply cleanup
  into Project Manager. Show exact eligible bytes, protected reasons and results there.
- [ ] Run cleanup and existing button/export tests; expect PASS. Manually confirm
  missing prerequisites produce reason + next action in the visible dialog.

## Task 4 / P11-C1: Bounded retention and disk admission

**Files:** Create `storage_policy.py`, `tests/test_storage_policy.py`; modify
`export_cache.py`, `service.py`, `working_export.py`, `storage_ui.py`.
Produces deterministic eviction choices and explicit policy activation.

- [ ] Add unit test `test_policy_preserves_pin_and_accounts_reservation` with
  three 1 GiB artifacts (old eligible A, recent eligible B, pinned C), budget 3 GiB
  and 1 GiB reservation: assert candidates `[A]`, retained 2 GiB, fits true.
  Add boundary tests at exactly 7 days, quota equals bytes, blocked pinned overage,
  archive larger than budget, concurrent reservations, and disk-full during server build.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_storage_policy.py -q`;
  expect missing-policy failures.
- [ ] Implement the pure policy; tie-break equal access timestamps by artifact ID.
  Add admin `PATCH /api/v1/storage/policy` with expected generation, validated
  max_bytes/max_age_days/automatic_enabled. Display impact preview before activation.
  Release legacy protection only for verified artifact IDs explicitly included in
  that reviewed activation preview; enabling policy alone never adopts unknown files.
- [ ] Invoke one policy engine at startup after activation, pre-build and every
  15 minutes. Count protected and busy bytes toward the total; no hard deletion of
  protected files to meet quota. Reserve build space before admitting concurrent work.
- [ ] Query free bytes for the configured server root only, preserve owned partial
  cleanup on failures, and show e.g. `Not enough cache space. Unpin an export,
  remove eligible cached exports, or increase the cache limit.`
- [ ] Run policy and working-export regression tests; expect PASS and no automatic
  deletion in the upgraded default-disabled configuration.

## Task 5 / P11-C2: Reuse equivalent exports and preserve historical semantics

**Files:** Modify `export_cache.py`, `working_export.py`, `export_ui.py`, `api.py`;
create `tests/test_export_cache_reuse.py`; extend `tests/test_working_export.py`.
Consumes registry and recipe key; produces single-flight builds and reprepare flow.

- [ ] Test `test_same_frozen_export_one_physical_zip`, `test_concurrent_prepare_single_build`,
  `test_review_checkpoint_mapping_and_converter_change_key`,
  `test_reuse_checks_project_role`, `test_evicted_export_reprepare_keeps_old_receipt`.
  Assert duplicate jobs may exist but physical artifact count is one; a new result
  never overwrites the old archive hash/result or uses current working annotations.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_export_cache_reuse.py -q`;
  confirm failures before implementation.
- [ ] Implement canonical key generation, uniqueness/reservation under transaction
  and coordination with eviction. Verify existing ZIP integrity before serving reuse;
  corrupt entries are unavailable pending explicit rebuild, not silently successful.
- [ ] Add `POST /api/v1/working-exports/{job_id}/reprepare` with Idempotency-Key:
  enforce project maintainer role, consume the old frozen snapshot and create a new
  job carrying source_job_id and explicit current recipe. Fail clearly if unsupported.
- [ ] Show availability/pin/reuse/new-converter status in export UI. Keep existing
  snapshot review-confirmation rules; history cannot be reinterpreted as approved release.
- [ ] Run reuse, working-export and checkpoint regression tests; expect PASS.

## Task 6 / P11-D: Deep asset reconciliation — report only

**Files:** Extend `storage_inventory.py`; create `tests/test_storage_asset_report.py`;
modify `cli.py`, `docs/operations-guide.md`.
Consumes Task 1 boundary and complete deep report. No backup path or apply interface.

- [ ] Test `test_registered_unused_asset_is_retained`, `test_expired_operation_still_pins_asset`,
  `test_old_file_only_orphan_is_reported_not_deleted`,
  `test_unknown_manifest_blocks_definitive_orphan_classification`,
  `test_external_backup_path_never_opened`, `test_report_never_rewrites_any_asset`.
  Assert every asset's contents/mtime are unchanged and outside-root opens are absent.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_storage_asset_report.py -q`;
  expect missing-report failures.
- [ ] Extend `storage-report --root ... --deep` with streamed hashes and full
  in-root historical reference traversal, disjoint category totals and 7-day orphan
  candidate classification. External or unreadable references mark classification
  incomplete; never open them or infer unreferenced status from their failure.
- [ ] Label orphan candidates `Report only; asset deletion is not available in Phase 11.`
  Do not add `storage-orphans-apply`, verified_backup inputs or a substitute backup
  under root. Explain retained history and unknown data in the report.
- [ ] Run asset-report and checkpoint regression tests; expect PASS. Document that
  all 4.63 GB may be required; Phase 11 does not promise to reclaim that difference.

## Task 7 / P11-E: Complete root-bound Storage UI

**Files:** Extend `storage_ui.py`; create `tests/test_storage_ui.py`; modify
`desktop.py`, `project_ui.py`, `feedback.py` only where shared feedback needs extension.

- [ ] Test `test_storage_shows_exact_configured_root`, `test_no_client_cache_scan`,
  `test_root_change_invalidates_ui_preview`, `test_external_report_destination_rejected`,
  `test_unknown_temp_is_report_only`, `test_storage_feedback_in_current_window`.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest tests/test_storage_ui.py -q`;
  confirm missing-feature failures.
- [ ] Display `Scope: <absolute configured root>` and `Only this root is scanned and
  managed.` in the window/preview. Do not add AppData, client-cache or external
  destination controls. A changed service/root discards pending reports and tokens.
- [ ] Finish root category totals, asset explanations, explicit units,
  retention settings and report creation under `reports/storage/`. Open report reads
  that validated server-root file through the API into the current UI without silently
  saving a client-side copy. Refresh remains cancellable/background;
  admin-only data is unavailable to other roles, with a reason and next action.
- [ ] Run targeted and button/export UI tests; expect PASS. Smoke at small viewport
  and Windows DPI settings to ensure totals, explanations and actions remain visible.

## Task 8 / P11-F: Scale, recovery, docs and package acceptance

**Files:** Create `scripts/storage_smoke.py`, `scripts/benchmark_storage.py`;
write `docs/verification-artifacts/phase11/storage-results.json` with synthetic summaries;
update `docs/phase11-plan.md`, `docs/operations-guide.md`, `README.md`,
`SoftwareExplainer.html`, `rush-wheel/README.md` and packaging version at delivery.

- [ ] Add small CI acceptance scenario: import → annotate/review → v1 → export twice
  → edit classes/add images → v2 → cleanup → restore/export v1 → backup/restore.
  Check source/annotation hashes, physical ZIP counts and history membership independently.
  Backup/restore compatibility uses a separate explicit synthetic fixture and the
  existing operations workflow, never a maintenance-triggered external directory scan.
  Add file-operation instrumentation and outside-root sentinels for management tests;
  unchanged contents alone is insufficient to prove no external reads/scans occurred.
- [ ] Run `.\.venv\Scripts\python.exe scripts/benchmark_storage.py --images 5400`
  after implementing a benchmark that creates isolated synthetic data outside the repo,
  reports path/free-space estimate before allocation and cleans only its own outputs.
  Record actual source bytes (do not assume PNG fixture compressibility), steady/peak
  usage per volume, timed scans, hits/evictions, and blocked versus reclaimed bytes.
- [ ] Run `.\.venv\Scripts\python.exe scripts/storage_smoke.py`; expect complete
  recovery and visible UI feedback, including expired cache/new export provenance.
- [ ] Run `.\.venv\Scripts\python.exe -m pytest -q`,
  `.\.venv\Scripts\python.exe -m ruff check src tests scripts`,
  `.\.venv\Scripts\python.exe -m ruff format --check src tests scripts`, and
  `.\.venv\Scripts\python.exe -m mypy src/visionlabel`; all must pass.
- [ ] Build/install/smoke the versioned application wheel using the existing packaging
  procedure; include requested wheel in `rush-wheel/` at authorized delivery. No new
  Python extension expected; existing native wheel remains compatible only if tested.
- [ ] Update phase status with measured evidence and remaining company acceptance.
  Do not claim a 9.6 GB saving on the company machine until its reviewed cleanup runs.
  Review focused diffs and commit/push only when authorized for this implementation.

## Planning self-review

- P11-A through F each have an owner module, runnable tests and output consumed by later tasks.
- Task 3 protects downloads before Task 4 enables eviction; Task 2 adopts provenance before either.
- Task 6 retains even unexplained registered assets, so uncertainty about 4.63 GB cannot trigger loss.
- User root-only clarification removed global client-cache work and deferred all orphan
  deletion. No maintenance task accepts an external backup/report/dataset path; Tasks
  1/3/6/7 include containment and no-outside-access evidence. Runtime staging is root-bound.
- Future preview-only export, inbox lifecycle, metadata purge and training pools are explicitly excluded,
  with rationale/destination in the phase specification; none is silently promised by this plan.
- Planning did not change runtime data. Subsequent authorized implementation is recorded in the execution ledger above.

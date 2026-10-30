# Phase 11 execution ledger

Plan: `docs/superpowers/plans/2026-10-28-storage-efficiency.md`
Spec: `docs/phase11-plan.md`; root-only clarification is binding.
Implementation authorized 2026-10-28. Branch: `codex/phase11-storage-efficiency`.

Ruling: continue in the existing checkout on a dedicated feature branch, preserving
the uncommitted reviewed plan and the existing Python environment. No extra
worktree/environment or production storage is needed. Do not commit/push without
authorization for this phase. Record progress here instead of bash-only skill helpers.

Pre-flight: Task 1 boundary/inventory feeds Tasks 2/3/6/7; every data operation
must use a validated root. Task 2 artifact registry precedes Task 3 eviction and
Task 4 policy. Task 5 reuse must share artifact/download locks with Task 3.
Task 6 is read-only, superseding the original orphan-delete interface.

Baseline: 358 tests passed before source changes. First integrated run: 384 passed.

Tasks 1–7: implemented and locally verified. Tests are
consolidated into test_storage_boundary/inventory/policy/cli/ui and test_export_cache
rather than the plan's proposed per-feature filenames. Task 8: local scale benchmark,
rendered smoke, documentation and wheel verification delivered; the measurement,
cancellation and company acceptance limitations below remain explicit open gates.

Ruling: legacy archives stay protected even after enabling automatic retention —
require explicit archive selection and cleanup preview to reclaim old exports;
cost: one additional reviewed step for the existing 13.9 GB cache.

Ruling: background storage requests use a bounded 20-minute HTTP timeout. Closing
the panel does not cancel a server mutation or deep scan. No server cancellation
protocol is introduced in this increment; cost: a scan continues until completion
and a timed-out user must refresh before retrying. UI remains responsive.

Ruling: scan totals measure logical file bytes, not allocated disk clusters. The
scale report labels transient peak as an estimate, not a measured peak. Cost:
physical space savings and worst-case peak still require company-disk acceptance.

Fresh review: gpt-6-astra reviewed the complete implementation and reproduced
three Important issues, with no confirmed Critical or Minor issues. All three
received failing regression tests before fixes: pinned export input reads,
recoverable unlink failure, and reprepare lineage excluded from cache identity.
Targeted RED: 3 failed. GREEN: 3 passed. Follow-up export/cache suite: 45 passed.
Staging additionally uses exclusive handle-based creation and verified handle
rename; failure cleanup removes only the owned file identity.

Review limit ruling: missing SQLite sidecar creation races were not reproduced.
Existing sidecars and all ancestor directories are pinned and checked; filesystem
ACL adversary resistance is not claimed. Cost: concurrent hostile local filesystem
tampering requires a dedicated security acceptance beyond ordinary storage use.

Rendered HTTP smoke: exact root, missing-selection feedback, root report read/write,
policy preview/apply passed. Visual inspection caught modal sequencing and clipped
labels; fixed before final capture. Windows DPI beyond this machine remains open.

Unrelated existing modification scripts/build_brand_assets.py is preserved.
No production root was scanned or cleaned, and no commits/pushes were made.

## Delivery evidence — 2026-10-30

| Area | Evidence | Result |
| --- | --- | --- |
| Boundary and report-only assets | test_storage_boundary.py, test_storage_inventory.py, test_storage_cli.py | Root/prefix/junction/replacement guards, history uncertainty and no asset deletion |
| Receipts, retention, reuse and recovery | test_export_cache.py, test_storage_policy.py | Pin/download protection, legacy registration, policy previews, idempotency, interrupted unlink recovery, checkpoint and backup/restore compatibility |
| UI | test_storage_ui.py; scripts/storage_smoke.py | Exact root, changed connection, local feedback, reports and policy workflow; rendered 700×570 window |
| Full regression | `.venv/Scripts/python.exe -m pytest -q` | 390 passed; one existing Starlette/httpx deprecation warning |
| Final UI/boundary follow-up | targeted pytest + storage_smoke.py after usage/status display change | 9 passed; rendered HTTP smoke passed |
| Static checks | ruff check, ruff format --check, mypy | All clean; 107 formatted files, 56 typed source files |
| Packaging | scripts/storage_wheel_smoke.py | Isolated pip target installation, schema 0009, GUI build and existing native extension compatibility passed |

Scale evidence: `verification-artifacts/phase11/storage-results.json`.
5,400 unique synthetic BMPs total **1,497,430,800 bytes**. Three different split
seeds produced three ZIPs; repeating the last frozen export reused its ZIP in
**6.50 seconds**, without a fourth image copy. The three builds took 107.51,
71.18 and 70.37 seconds. Deep scan took 57.12 seconds. Reviewed retention reduced
cache from **4,514,061,297** to **3,009,374,198 bytes**, reclaiming **1,504,687,099
bytes**. All 5,400 assets and all three receipts remained; no scan warnings.
The benchmark uses a deliberately tightened budget of 3,009,375,222 bytes to
exercise eviction (the product default remains 4 GiB).

The long scale process was launched before the final review hardening; its numbers
describe that run, not a new performance measurement of the final wheel. The final
implementation also passed the 30-image end-to-end benchmark in
`storage-final-smoke.json`, plus the full regression suite. No claim is made about
the company's disk, exact allocated clusters, transient measured peak, alternate DPI,
or LAN throughput. Earlier approved-release/company gates remain unchanged.

Application wheel: `rush-wheel/visionlabel-0.1.5-py3-none-any.whl`.
SHA256: `90a0502e591bef4b7478c6f7108613c386f94ac8ca973a2966f6b75ec546043b`.
No new native extension; existing native 0.1.0 was tested. Runtime dependencies are
unchanged; uv lock check and both README export commands passed. The wheel was
built with pip build isolation because hatchling is not installed in the existing
development environment; no global package/environment changes were made.

No deferred minor review findings. The Important review findings were fixed and
the full suite passed after the fix pass. An added handle-publication regression
also caught a missing UTF-16 terminator; it was fixed and verified before packaging.

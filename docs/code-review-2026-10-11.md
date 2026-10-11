---
reviewed: 2026-10-11
revision: a6bf95e
depth: deep
status: issues_found
remediation_status: fixed_and_locally_verified
findings:
  critical: 1
  warning: 5
  info: 0
  total: 6
---

# Project code review

Review of the current project on `develop`, prioritizing annotation usability,
lease/recovery behavior, project permissions, and working export correctness.
This is a review, not an implementation or a phase acceptance sign-off.
During the original review, no application source was changed.

The review above describes the original findings at `a6bf95e`. The subsequent
authorized remediation is recorded at the end of this document.

## Narrative Findings (AI reviewer)

### P1 — Export mapping can change while an older export is being prepared

**Location:** `src/visionlabel/export_ui.py:225-228`; related lines 209-222, 520-523.

`set_busy()` disables ratios and seed but leaves `export_mapping` editable.
Changing that field during preparation calls `invalidate()`, which skips clearing
the prepared request while busy. The completion callback then accepts the result
for the earlier mapping and enables Save. The displayed mapping and the exported
class indices can therefore disagree, silently producing the wrong model class
mapping for training.

**Evidence:** A delayed-submit headless probe starts preparation with the default
mapping, edits the mapping while busy, and completes the original request. The
mapping widget was not disabled; the submitted mapping remains the old value,
the displayed mapping contains the new value, and Save becomes enabled.

**Fix:** Disable mapping changes during preparation, and/or bind completion to a
settings generation and reject results if the options changed. Add a delayed
completion regression using a valid two-class index swap.

### P2 — Failed image loading leaks the newly acquired lease

**Location:** `src/visionlabel/desktop.py:819-832`; failure handler at 904-906.

After acquiring a claim, annotation/history/content retrieval, decoding, texture
conversion, or draft loading can fail before the claim reaches `self.claim`.
The failure callback reports the error but neither retains nor releases that
claim. Retrying uses a new idempotency key. The service rejects even the same
client while that claim is active, so a transient load failure can leave the image
read-only for the 900-second lease period.

**Evidence:** Stub the annotation GET to raise `DISCONNECTED` after a successful
claim POST. After `open_image` fails, `Desktop.claim` is `None` and no claim DELETE
was issued. `service.py:575-579` rejects the existing unexpired claim and assigns
a 900-second expiry. Other-image navigation still works; this is a bounded
per-image lockout, not a permanent application lock.

**Fix:** Make lease acquisition exception-safe. Release the acquired claim after
downstream loading failures, or retain its handle/key so retry can recover it.
Also handle an uncertain claim acknowledgement without discarding its retry key.

### P2 — Autosave prevents the recovery navigation it tells the user to perform

**Location:** `src/visionlabel/desktop.py:959-965`; related lines 1036-1041.

If a dirty editor becomes blocked after heartbeat failure or lease expiry,
guarded navigation with Autosave enabled always calls `save()`. That method
clears the navigation continuation and tells the user to reload, but Reload is
itself guarded and takes the same failing path. No keep-local/reconciliation
choice is displayed in this path. The user must discover that disabling Autosave
first allows the existing dirty-navigation dialog to appear.

**Evidence:** A dirty, blocked editor with Autosave enabled passed to `guard()`
does not execute the destination, does not show `dirty_dialog`, and clears
`next_action`; it only displays the reload/reconcile message. Heartbeat failure
can set `blocked` without opening the save-conflict dialog.

**Fix:** Route blocked/unclaimed dirty editors to explicit draft-preserving
recovery choices instead of attempting navigation autosave.

### P2 — Class changes and deletion during a rectangle drag are overwritten

**Location:** `src/visionlabel/desktop.py:591-602` and `1168-1189`;
related `src/visionlabel/canvas.py:98-99,138-144`.

Class selection and Delete can mutate the editor while a rectangle gesture is
active. The gesture holds a snapshot of the older content, and `finish()` writes
that snapshot-derived preview back into the editor. A numeric class shortcut
during a drag can revert to the old class on mouse release; deleting the shape
during the drag can resurrect it.

**Evidence:** Start a rectangle move, invoke `Desktop.select_class()` with a new
class, then finish the gesture. The probe observes the new class immediately
after selection and the old class after finishing. The deletion path has the
same snapshot overwrite.

**Fix:** Finish or cancel the active gesture before these mutations, or suppress
the corresponding commands until the gesture ends. Verify both class selection
and deletion while moving/resizing.

### P2 — A shared-project maintainer cannot edit metadata while preserving its folder

**Location:** `src/visionlabel/project_tools.py:63-64`;
related `src/visionlabel/project_ui.py:315-324`.

Updating project metadata unconditionally calls `manage_folder()` for the
submitted folder, even when it has not changed. That check requires folder
ownership or system admin status. A non-admin project maintainer cannot rename,
describe, or archive a project stored in another user's folder, despite having
the project capability. The desktop submits the current folder with ordinary
metadata edits.

**Evidence:** Create a project in the creator's folder, add a second non-admin
maintainer, then PATCH its name while preserving `folder_id`: 404, `Folder not
found or not managed by this account`. The same update with `folder_id=None`
succeeds, demonstrating that the unchanged folder blocks the authorized edit.

**Fix:** Require folder-management permission when the folder assignment changes;
allow otherwise-authorized metadata edits to preserve the current folder.

### P2 — The working split allocator rejects a feasible class-covered split

**Location:** `src/visionlabel/working_export.py:95-104`.

The initial class-coverage pass can select separate singleton-class groups for
train. Populating empty partitions then permits only individual moves that keep
the current train coverage. It reports `TRAIN_COVERAGE` when a group exchange
would satisfy the constraints, incorrectly telling users to add data or remove
the test partition.

**Reproduction:**

```python
from visionlabel.working_export import split_items

def cid(n):
    return f"00000000-0000-4000-8000-{n:012d}"

items = [
    {
        "image_id": cid(i + 1),
        "asset_sha256": str(i) * 64,
        "group_key": None,
        "class_ids": [cid(c) for c in classes],
    }
    for i, classes in enumerate([[100], [101], [100, 101]])
]
split_items(items, {"validation_percent": 20, "test_percent": 10, "seed": 4})
```

This raises `TRAIN_COVERAGE`. The valid assignment is image 3 to train, image 1
to validation, and image 2 to test. Both classes exist in train, every requested
partition is populated, and all asset/group boundaries are preserved. Ratios
are documented targets, not exact constraints.

**Fix:** Try deterministic exchanges/reselection before declaring failure, and
distinguish heuristic allocation failure from proven infeasibility.

## Verification and limits

- `.\.venv\Scripts\python.exe -m pytest -q`: **252 passed**, one existing
  Starlette/httpx deprecation warning; 122.84 seconds.
- `.\.venv\Scripts\python.exe -m ruff check src tests scripts`: passed.
- `.\.venv\Scripts\python.exe -m mypy src`: passed, 38 source files.
- Additional synthetic and headless probes reproduced the findings above.
- No physical mouse/DPI, live two-machine LAN/SMB, or company dataset acceptance
  was performed. GUI findings were traced through callbacks with stubbed UI and
  asynchronous responses; this review does not claim a new rendered smoke run.
- Existing released-version, packaging, and earlier phase integration gaps are
  retained as documented scope limitations, not reported as newly found bugs.

Review coverage included the service/API/database/storage/review/project-tools
paths; desktop/canvas/client/review/team/project UI; export/format/split/legacy/
operations paths; and supporting domain, contracts, imaging, statistics,
launcher, preview CLI, and offline installer code. This is risk-focused coverage,
not a claim that every possible execution path was exhaustively verified.

## Authorized remediation — 2026-10-11

Implemented on `codex/fix-review-findings` after user authorization:

| Finding | Change | Regression evidence |
|---|---|---|
| Stale export mapping | Disable class mapping alongside ratios/seed throughout preparation; re-enable after completion/failure | Delayed prepare response and mapping-control availability in `test_export_ui.py` |
| Leaked load claim | Release claims on downstream load failures; retain unresolved handles or original acquisition key for cleanup retry before the next load | Annotation/history/decode/draft failures, failed release, and lost claim acknowledgement in `test_phase9_desktop.py` |
| Blocked autosave recovery | Show draft-preserving navigation choices when save is unavailable; disable Save and continue in that state | Blocked and claimless editor navigation with Autosave enabled |
| Gesture overwrites | Cancel the unfinished drag before applying class/delete commands; retain the last committed geometry | Class change and deletion both survive the subsequent mouse release |
| Shared maintainer metadata | Check folder ownership only when assigning a different non-null folder | Non-admin maintainer can rename/archive while retaining the existing folder, but cannot move into another user's folder |
| False split infeasibility | If greedy allocation cannot populate every requested partition, reselect one/two whole evaluation groups while preserving all training classes | Original failing seeds, reversed input order, genuinely impossible coverage, and exhaustive feasibility comparison for small inputs |

The split report now identifies algorithm `working-group-split-2`. The archive
profile remains `working-yolo-export-1`; existing artifacts are not rewritten.
The original seeded ordering is retained. Fallback selects one group per requested
evaluation partition and puts the remainder in train; ratios remain targets and
the actual counts/percentages remain visible. With at most two evaluation
partitions, only classes carried by one or two effective groups can prevent
holding out those groups. The fallback uses those constraints to determine
feasibility while preserving connected image-group/asset boundaries.

The fixes preserve working-export status as unreviewed and do not close any
released-version, company LAN/SMB, or physical mouse/DPI acceptance gates.

### Post-fix verification

- Focused affected-module suite: **84 passed**.
- Full suite: **276 passed** in 107.34 seconds; the same existing
  Starlette/httpx deprecation warning remains.
- Ruff lint, formatting of all changed Python files, mypy (38 source files), and
  `git diff --check`: passed.
- `scripts/desktop_smoke.py`: **passed**, using a real rendered desktop and
  loopback HTTP service with synthetic data. Checks include rectangle save/reload,
  delete/undo, class changes, recovery, autosave, polygon persistence, prediction
  import, working export/download verification, diagnostics, mapping, and project
  management. This is automated rendered evidence, not human mouse/DPI acceptance.
- Local smoke evidence: `C:/Users/Minotaur/AppData/Local/Temp/visionlabel-review-08cc6b7126964ca381b202386b5671eb/desktop-smoke.json`.
- No dependency changes, merge, or push were performed.

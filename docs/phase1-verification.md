# Phase 1 verification and remaining acceptance

Status: the user accepted the local Phase 1 milestone and explicitly authorized
Phase 2 after confirming classification, zoom/pan/drag/fit, close/reopen persistence,
and DPI operation. Automated evidence and the scope of human feedback are recorded
separately below; this is not a production release qualification.

## Requirement-to-test matrix

| Requirement / invariant | Implementation | Evidence |
|---|---|---|
| Phase 0 contracts / serializer | contracts.py, domain.py, frozen JSON schema | Exact-byte decimal/UTF-8 tests, semantic validation, saved-document JSON Schema validation |
| PR01 / PR02 | Project/initial class schema creation, UUID identities | API integration tests, schema snapshots; subsequent schema changes remain Phase 3 |
| PR03 / T10 | Inbox ingestion, WIC decode worker, SHA identity | 100-image import, duplicate detection, path/format failures; bounded decoder |
| PR04 | Cursor pagination, filename/status browser | Pagination coverage and changed-filter cursor rejection; remaining team/QC filters in later phases |
| PR05 | Rectangle canvas and Editor command history | Four drag directions, bounded movement, resizing, undo/redo, transform and handle-hit tests, rendered HTTP smoke |
| PR07 | Single-label classification | Classification revision round trip and completeness validation |
| PR08 | Explicit empty content flag | Empty/classification distinction tests; submit/review status transitions remain Phase 2 |
| PR09 / T01–T03 | Edit lease, heartbeat, counters, fencing | Barrier-driven claim/save races, stale save, revoked/expired/restarted claims |
| PR11 / T04–T05 | Debounced save, idempotency, DPAPI drafts | Lost-response replay; fault boundaries; actual child-process exit after publish/commit; encrypted draft round trip and rendered recovery/autosave smoke |
| PR12 | Transactional audit | Stable shape created/updated/deleted IDs in revision audit tests; history/audit browser remains Phase 2 |
| PR18 / T17–T18 | Permission checks, root containment, offline backup | Cross-project/viewer tests, token revocation during save, UNC/mapped-drive rejection, backup/restore with exact blob hash |
| PR18 / packaging | Wheel plus pinned runtime dependencies | Independent environment install and render smoke; Nuitka/clean-machine packaging remains Phase 6 |

## Evidence commands

Run the commands in README.md to reproduce the results. Automated desktop smoke
calls application/controller actions in a rendered window; it is not a claim that
physical mouse gestures, screen scaling, or user ergonomics have been manually tested.

- Unit/contract/integration/security/recovery suite: **46 passed** at the recorded run,
  including exact decimal request preservation at a rounding boundary.
- Ruff lint and formatting, and mypy: checked as part of the implementation.
- Rendered desktop smoke: real server login, import, rectangle drag, save/reload,
  delete/undo, class change, explicit draft recovery, two-second autosave, and
  full-image crosshair geometry with Select/pan/outside-image suppression.
  The refreshed screenshot is in `verification-artifacts/rectangle-workspace.png`.
- Actual crash tests: process terminates with `os._exit` after file publication and
  after DB commit; restart verifies head/hash and replay semantics.
- Independent wheel install/render: see generated package-smoke.json from
  scripts/package_smoke.py. Do not equate this with a production installer.
- One known warning: the installed Starlette test helper deprecates HTTPX in favor
  of its newer test transport. HTTPX tests currently pass; no runtime migration
  from the specification's HTTPX baseline has been made.

## User acceptance and further manual coverage

User feedback confirms administrator creation, project creation, rectangle drawing,
class selection, keyboard shortcuts, classification, zoom/pan/drag/fit, and unchanged
data after closing/reopening. The user subsequently confirmed DPI works and asked
to start Phase 2. The exact Windows Scale percentage was not reported; do not claim
that all four percentages below were tested. The requested full-image Rectangle
crosshair is implemented and rendered-smoke checked.

- [x] User confirmed close/reopen persistence.
- [x] User confirmed zoom, pan, drag, fit and shortcuts.
- [x] User confirmed DPI operation on their setup (percentage unspecified).
- [x] User confirmed single-label classification.

The following detailed coverage has not been individually reported. Retain it
for further verification; do not infer completion from the general acceptance:

- [ ] A user performs import -> draw -> move -> resize -> save -> close/reopen.
- [ ] Physical mouse selection/handles, scroll zoom, Space+drag and all shortcuts feel reliable.
- [ ] Shortcuts do not interfere with typing into search, project fields or comments.
- [ ] Test actual Windows display scaling at 100%, 125%, 150% and 200%.
- [ ] Check Unicode filenames/class names and window resizing on the user's monitor.
- [ ] Disconnect/stop the server, edit locally, reconnect and reconcile a draft without overwrite.

## Scope and operational notes

This milestone is loopback-only and has no team/review UI, release/split/export,
polygon editor or training dependency. Those requirements retain their specified
phases. Basic backup was brought forward to protect pilot data; scheduled online
maintenance backup remains later. No confidential data was used in tests.

The complete Phase 6 targets (10 clients, 50,000-image performance, blocked-egress
OS test, clean-machine install, final native build SBOM and operator restore drill)
are not claimed by these development-machine checks.

Draft retention deliberately favors preserving unresolved work: cache is bounded
to 1 GiB / 30 days, while recovery and archived comparison drafts remain until
resolved. A configurable draft-retention policy and UI cleanup controls are
recorded for PR18 / Phase 6, with no silent deletion of unsaved annotations.

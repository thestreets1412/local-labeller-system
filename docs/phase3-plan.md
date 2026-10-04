# Phase 3 progress and verification

Status: increment 1 implemented (polygon editor and working statistics/QC).
Phase 3's immutable-release exit gate is still open.

The user subsequently requested Phase 4. Its independent algorithm preview may
proceed, but this document's remaining review/release/schema requirements stay
open. No mutable working snapshot is substituted for a released split source.
See `phase4-plan.md` for the current engine increment and integration prerequisites.

## User-authorized sequencing

The user accepted the local account/membership increment and requested Phase 3.
They work on one home PC and can only test actual client machines after cloning
at the company. Record unavailable tests separately from unfinished features.

| Requirement | Decision and rationale | Destination / completion condition |
|---|---|---|
| PR06, PR14 | Start polygon editing and saved working statistics now; independent of LAN deployment | Phase 3 increment 1 |
| PR04, PR08, PR09 | Assignments, claim-next, workflow transitions and team filters remain unimplemented; cannot be marked passed by account tests | Phase 2 follow-up integration, retained in phase2-plan.md |
| PR10 | Review UI and revision/hash-bound approval are not implemented; release must never fabricate approvals | Phase 2 follow-up before Phase 3 reviewed segmentation / approved releases |
| PR12 | Mutation audit persists, but history/audit browsing and restore UI remain open | Phase 2 follow-up integration |
| PR18 | LAN HTTPS/SMB support is not implemented; current build remains loopback-only | Phase 2 deployment increment |
| PR09, PR10, PR18 | Actual two-client/two-machine and share-denial acceptance unavailable at home | Company verification after deployment support, before marking the team exit gate passed |
| PR02, PR13, PR14 | Stable schema migration, version release/manifests, version browser/diff and released statistics remain open | Subsequent Phase 3 increments; no scope removal |

This changes work order, not the required integrity model or production acceptance.
Local tests, independent client sessions, concurrency, validation, migrations,
and crash checks continue where possible. No requirement is silently discarded.

## Implemented increment

- Segmentation project creation and Alembic migration 0003; existing project IDs,
  schema identities, image links, annotations, and artifact bytes remain unchanged.
- Polygon click-to-add, Enter/double-click/first-point close, Escape cancel,
  select/move, screen-sized vertex handles, vertex drag/delete, double-click-edge
  insertion, shape deletion, undo/redo and the existing API save/autosave/recovery.
- Geometry validation before accepting an edit and again on the server: bounds,
  distinct vertices, positive area, nonintersection, canonical winding/start and
  six-decimal rounding. Failed vertex edits preserve the last valid shape.
- Unfinished points stay local UI state. Navigation/save prompts require finishing
  or cancelling; autosave never publishes an incomplete polygon. Closing the native
  window preserves completed edits via recovery; unfinished points are not persisted.
- Read-only Statistics / QC reports on saved working annotations: per-class image
  and object counts, statuses, verified empty, groups, formats, resolutions, class
  imbalance, unlabeled/missing-group/tiny-shape warnings. Classification labels
  count as image presence, not geometry objects. Current-schema entries are used;
  future schema migration must extend reporting across historical class identities.
- Statistics capture heads in a consistent SQLite read snapshot, then read immutable
  annotation blobs with hash verification. Each report identifies its source
  snapshot; it does not claim to verify source asset bytes or a released version.
- Administrator member onboarding: select a user directly in Project members,
  choose a role, then Add / update role. Maintainers still use supplied user IDs
  for accounts outside their project's membership; no global directory is exposed.
- Project switching clears stale image rows and rejects a load from another project.

## Evidence

- Automated suite: **73 passed**, including 19 polygon/QC/migration cases.
- Ruff lint/format and mypy: passed.
- Exact-byte polygon golden expectation covers winding and starting-vertex changes.
- Invalid/degenerate/self-crossing/out-of-bounds/rounding-collapse inputs rejected;
  pointer transforms and handles exercised at multiple scales.
- API polygon save/reload validated against the annotation JSON Schema.
- Migration from an actual 0002 database preserves populated project/annotation
  tables and annotation bytes; foreign-key enforcement remains enabled afterward.
- Working statistics tested for distinct image counts vs object counts, empty vs
  unlabeled, stable source signature, and annotation corruption rejection.
- Rendered real-HTTP desktop smoke covers rectangle regression, direct member
  picker, segmentation drawing/vertex movement/save/reload, and working QC.
- Independent offline wheel install includes new modules/migration and renders
  outside the source tree. Not a clean-machine or two-machine qualification.

See `verification-artifacts/polygon-workspace.png`, `working-statistics.png`,
`team-members.png`, and their JSON smoke reports. The known Starlette TestClient
HTTPX deprecation warning remains; no dependency changes were introduced.

## Still to verify with the user

- Physical click/double-click, edge insertion, vertex editing and shortcuts feel
  reliable on the user's mouse and actual Windows display scale.
- Confirm the simplified member picker is discoverable without the guide.
- Company-only LAN/two-PC/SMB checks remain unperformed by explicit agreement.

## Remaining Phase 3 implementation

1. Integrate PR10 review evidence and reviewed segmentation; enforce self-review
   policy and stale approval rejection before exposing release actions.
2. Class schema creation/migration with stable IDs, explicit mappings, dry-run
   reports and no rewriting of historical annotations.
3. Immutable dataset release jobs/manifests, pinned assets/schema/groups/reviews,
   interrupted-publication recovery and backup coverage for new artifacts.
4. Version browser, semantic diff with golden fixture, and version statistics.
5. Verify v1 bytes/hashes remain unchanged after v2, corrupt/missing assets block
   release, and schema changes never reinterpret historical labels.

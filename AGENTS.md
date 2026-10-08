# Repository guidance

## Product and priorities

- Build VisionLabel (Windows desktop annotation) and DataTracking (LAN service) according to `VisionLabel_DataTracking_Specification.md`.
- The user's immediate priority is a smooth, reliable rectangle annotation workflow. Prioritize rectangle create/select/move/resize/delete, zoom/pan, class selection, keyboard shortcuts, undo/redo, save/load, autosave, and recovery.
- Follow Phase 0 through Phase 6 and their exit gates. Within Phase 1, prove import -> claim -> rectangle -> save -> reload first, then complete the remaining Phase 1 requirements, including single-label classification. Do not silently drop or defer requirements.
- Record proposed scope changes with requirement IDs, rationale, and the destination phase. Do not add polygon UI, team workflow UI, or export ahead of the rectangle milestone unless the user changes priorities.
- User sequencing override: after accepting the local Phase 2 account/membership increment, the user requested Phase 3 now. Implement and test what is possible on the home PC; defer actual two-machine/LAN/SMB acceptance to the company environment. This does not mark unfinished Phase 2 implementation complete. Track its remaining PR04/PR08/PR09/PR10/PR12/PR18 work, and complete revision-bound review prerequisites before implementing approved dataset releases. See `docs/phase3-plan.md`.
- Further user sequencing override: start Phase 4's independently testable split engine before Phase 3 releases exist. Standalone diagnostic previews are not canonical splits. Keep release verification, split persistence/jobs, GUI and export integration pending; do not substitute mutable working data for released-version input. See `docs/phase4-plan.md`.
- The user next requested Phase 5. Start PR16 format conversion and PR17 read-only legacy dry-run independently; these do not approve data, import revisions or publish training exports. Track release/split adapters, canonical import, jobs and GUI as pending integration in `docs/phase5-plan.md`.
- The user requested Phase 6 next. Harden existing operations and provide an offline development installation kit independently; retain all earlier integration gaps and do not claim production readiness, Nuitka packaging or company acceptance from local wheel tests. See `docs/phase6-plan.md`.
- User-requested Phase 8 permits practical YOLO training exports from a frozen snapshot of saved working annotations before reviewed releases exist. Support detection, segmentation and classification, validation/test percentages and a client-local destination, including single-PC admin use. Explicitly identify working exports as unreviewed, preserve source hashes/revisions and group/asset boundaries, and never claim these artifacts satisfy the pending reviewed-release gates. See `docs/phase8-plan.md`.

## Product language

- Phase 8 follow-up authorized 2026-10-07: implement aggregate export diagnostics
  first, then inspect/revalidate, bounded quantization, class mapping, project
  management/folders and version history according to `docs/phase8-follow-up-plan.md`.
  Keep model export mapping separate from stable class identity and project folders
  separate from image split groups. Working snapshots are not approved releases.

- User-requested Phase 7 connects same-stem YOLO detection text files to canonical
  editable predictions and adds BMP alongside PNG/JPEG. Implement the desktop path
  and real persistence; preserve lease/revision safeguards and never overwrite
  existing annotations during prediction import. See `docs/phase7-plan.md`.

- All application-authored UI text, menus, buttons, tooltips, validation/error messages, dialogs, and installer text must be English. No Thai localization or language switcher is planned for v1.
- User-provided filenames, paths, class names, project names, and comments remain Unicode-capable; English UI does not restrict user data to ASCII.
- Repository discussions and the specification may remain in Thai. Identifiers, API contracts, and schemas use English.
- Bundle any required fonts locally and verify their licenses; do not fetch fonts at runtime.

## Environment and repository workflow

- Use the existing `.venv` with Python 3.12.10. Invoke `.\.venv\Scripts\python.exe` explicitly when running Python tools; do not rely on bare `py`, which currently defaults to Python 3.14 on this machine.
- Do not recreate the environment or install packages globally. Pin dependencies in a reproducible lockfile when dependency tooling is established.
- Support end-user installation with Python's bundled pip; uv is optional on the destination machine. When changing dependencies, update `uv.lock` and regenerate both `requirements.txt` and `requirements-dev.txt` using the commands in README. Keep the local application entry so `pip install -r requirements.txt` installs the application as well as its dependencies.
- `develop` is the integration branch. Inspect Git status before edits and preserve user changes. Use focused `codex/` branches for implementation work unless directed otherwise; do not merge or push without user authorization.
- Keep confidential datasets, runtime databases, caches, recovery drafts, secrets, and build output outside tracked source. Use synthetic test data.

## Architecture and integrity

- Keep the baseline stack: Dear PyGui, FastAPI, SQLAlchemy/Alembic, SQLite on server-local disk, and immutable managed files. Do not introduce a web frontend or additional infrastructure by default.
- The service is the only canonical writer. The desktop must never write SQLite or canonical annotations/assets directly, including in single-user development.
- Keep domain logic independent of GUI, HTTP, and ORM code. Share explicit client/server contracts.
- Implement real leases, fencing generations, expected content/state revisions, authorization, audit, and idempotency for the initial save workflow. Phase 2 expands team behavior; it does not introduce a replacement persistence model.
- Publish durable immutable files before committing DB pointers; recheck lease, permissions, schema, and counters in the commit transaction. Never silently overwrite stale data.
- Preserve raw image bytes, original raster coordinates, and the no-auto-EXIF-rotation policy. Keep image-to-screen coordinate conversion centralized.
- Freeze serialization rules with exact-byte golden fixtures before relying on hashes. Never rewrite historical artifacts after changing serialization behavior.
- Released versions, splits, and exports must reference immutable inputs. Follow the specification for review binding, class identity, and reproducibility.
- Use only dependencies and bundled components that meet the specification's license policy. Do not bundle Ultralytics or LabelMe runtimes.
- User-approved exceptions (2026-10-03), with notices required: certifi under MPL-2.0; typing_extensions under PSF-2.0; NumPy components under 0BSD, Zlib, and CC0-1.0. These are specific exceptions, not a blanket expansion to other packages or licenses.
- Additional user-approved exception (2026-10-03): FreeType under FTL as bundled in Dear PyGui, with attribution and retained notices. Do not select its GPL alternative.
- Runtime operation must remain LAN-only without telemetry, cloud calls, external fonts, or update checks.

## Implementation and verification

- Work in small runnable increments with observable saved/loading/error/conflict states. A UI mock is not evidence of persistence or a completed phase.
- Map requirements to tests and phase exit gates. Test behavior with independent expected results, especially serialization, geometry, concurrency, crash recovery, and export conversion.
- Check rectangle usability manually: drag in every direction, selection and resize handles at different zoom levels, cursor-centered zoom, pan, DPI, text-input shortcut suppression, and dirty navigation.
- Perform an early Windows packaging/font smoke check. Have a verified basic backup/restore path before using valuable real data; complete production packaging and operational drills in Phase 6.
- Report what changed, which checks ran, and remaining limitations. Do not claim a phase complete without its exit-gate evidence.
- Document architectural decisions and contract clarifications. Follow explicit user instructions when they revise the baseline, and update affected documentation consistently.

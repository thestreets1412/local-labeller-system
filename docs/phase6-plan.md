# Phase 6: operations and offline deployment increment

The user requested Phase 6 after the format/dry-run increment. **Phase 6 and the
global production Definition of Done are not complete.** This increment hardens
existing backup/restore and delivers an executable offline development wheel kit.
It does not qualify the unfinished team/release/split/export workflows for release.

| Requirement / gate | Implemented this round | Remaining destination |
|---|---|---|
| PR18, §16, Phase 6 backup | Read-only verify-backup, staged backup/restore publication, copied-byte verification, failure tests | Phase 6 fresh-PC restore and hard process/power-loss drills; future version/split/export reference coverage |
| PR18, Phase 6 offline installation | Exact locked runtime wheel provisioning, manifest hashes, notices/SBOM, installer with no-index/hash-required pip, local launcher | Phase 6 Nuitka Windows builds, clean-machine installer, service registration and production qualification |
| Phase 6 documentation | Operator guide: inbox, offline kit, backup/restore, sensitive data, recovery, planned company HTTPS acceptance | Runnable HTTPS/service setup once LAN implementation and company CA/identity are available |
| PR10/13/15/16/17 | No false acceptance; earlier plans remain authoritative | Phase 2 revision-bound review, Phase 3 release, Phase 4 canonical split, Phase 5 export/import integration |
| PR04/08/09/12/18, PR02/14 | Still listed in phase2/3/4 plans | Team workflow, audit/history, schema migration/version diff and LAN implementation |
| Phase 6 performance/security acceptance | Not claimed by wheel or unit tests | 10-client measurements, disk-full save/reconnect/restart matrix, blocked external egress, two-PC company journeys |

## Operational behavior

- Backup holds the existing exclusive service-directory lock while taking a SQLite
  snapshot and copying every referenced immutable asset/schema/annotation blob.
  It writes the COMPLETE manifest in private staging, verifies it and publishes a
  new directory by same-volume Windows rename. Existing destinations are refused.
- Restore validates manifest schema, duplicate paths, database integrity/FKs and
  exact reference/hash/size coverage. SQLite sidecars are rejected and verification
  opens the snapshot read-only/immutable so it does not modify backup files.
- Restore stages copied bytes, rechecks their hashes before using the database,
  expires claims, revokes tokens and fails interrupted jobs, then publishes. Ordinary
  exceptions remove private staging; hard termination may leave orphan staging,
  which operators must never treat as a published destination.
- New `datatracking verify-backup` command works without a live service. CLI I/O
  errors are concise English messages with nonzero exit status.
- Staged publication and fsync improve failure handling but do not constitute a
  tested guarantee against hardware/controller power-loss behavior.

## Offline kit

See [operations-guide.md](operations-guide.md) for exact commands. The build script
provisions dependencies from the current lock with wheel hashes, builds the current
app source into a wheel, includes license notices and the existing inventory/SBOM,
then hashes every kit file. It refuses an existing output directory. Installation
requires a separately provisioned Windows x64 Python 3.12.10 and a new target folder.
No global packages or existing repository environment are modified. Kit manifests
are integrity checks, not signatures or source-control commit provenance.

`scripts/offline_kit_smoke.py` installs the actual kit into a temporary environment
outside the checkout, runs packaged migration/backup/verify/restore/login and renders
the desktop. `tests/test_operations.py` uses real synthetic image/annotation data
for recovery, hash preservation, Unicode paths and session invalidation. It injects
copy/flush failures and corruption without touching the user's live dataset.
`tests/test_offline_kit.py` checks altered wheels, path escape and unlisted files.

No Windows scheduled task, firewall rule, certificate or service is installed by
this increment. The operator guide distinguishes an offline maintenance schedule
from an unimplemented managed service/online backup scheduler. Nuitka/compiler
dependencies and their bundled-license review remain pending; the wheel kit does
not replace that production deliverable.

## Recorded checks (2026-10-04)

- **160 tests passed**, including 19 new operational/kit cases. One existing
  Starlette TestClient/HTTPX deprecation warning remains.
- Ruff lint and formatting passed for 50 Python files; mypy passed for 29 source
  files. PowerShell parser validation passed for the launch script.
- Built `dist/offline-kit-phase6` and verified all 79 listed files. The complete
  kit remains ignored build output; copy the whole directory when transferring it.
- Actual offline installation, packaged initialization/backup/restore/login and
  desktop rendering passed outside the checkout. Evidence:
  `verification-artifacts/offline-kit-smoke.json` and `offline-kit-desktop.png`.
- Kit manifest SHA-256:
  `3f637f28bb8aeccbd4d829a5af25d8ea56035f50029d415b69336026a9aa9d6a`.

The tests used temporary synthetic data, not the user's live data directory. No
commit, merge, push or machine-wide deployment configuration was performed.

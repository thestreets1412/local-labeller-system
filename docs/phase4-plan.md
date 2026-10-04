# Phase 4: deterministic split planning

Status: the independently testable split engine and developer preview CLI are
implemented. Phase 4's end-to-end exit gate is **not complete**. There is no desktop
split button, released-version adapter, canonical split record or export integration.

## User-authorized sequence and dependencies

The user requested Phase 4 after the polygon/QC increment. Preserve the unfinished
earlier requirements instead of interpreting the request as acceptance of them.

| Requirement | Current work / rationale | Required destination |
|---|---|---|
| PR15 | Four deterministic strategies, leakage protection, pins, diagnostics and comparison implemented independently | Phase 4 engine increment |
| PR15 | Seed/ratio GUI, immutable split manifests, jobs and persistence remain open because no released version exists to select | Phase 4 integration after PR13 release |
| PR10, PR13 | Reviewed segmentation, approved releases and frozen manifest verification are still prerequisites, not simulated inputs | Phase 2 review / Phase 3 release follow-up |
| PR02, PR14 | Class schema migration, version browser/diff and released statistics remain open | Phase 3 follow-up |
| PR04, PR08, PR09, PR12, PR18 | Other team workflow, audit browser and deployment work remains listed in phase2-plan.md | Phase 2 follow-up |
| PR09, PR10, PR18 | Actual two-machine/LAN/SMB acceptance remains unavailable at home | Company setup after implementation; explicitly deferred by the user |

The preview reads an explicit frozen projection file. It never reads current DB
heads, asserts release approval, or writes canonical dataset/split/annotation state.
Its artifact flags say `canonical_split=false` and `provenance_verified=false`.
`PASSED` means the supplied projection meets this configuration's constraints;
it does not authorize training export or prove source authenticity.

## Algorithm contract: vl-split-1

- Normalize input/config through strict models; sort image and class IDs. Reject
  duplicate image IDs, unknown classes, incomplete labels, invalid ratios/seeds,
  unsupported versions and unknown fields. Classification has one class per image.
- Same asset hash always forms one connected component. Group strategies also
  union equal non-null group keys, including transitive group/hash connections.
  Missing keys use explicit error/singleton policy; enforce_group_split cannot be
  bypassed by choosing random/stratified. Non-group strategies warn on group data.
- Count class **image presence**, not objects. Use `__empty__` for verified-empty
  background balancing. Coverage checks include that observed pseudo-class;
  unused schema classes appear with zero counts but are not balance objectives.
- Largest remainder sets integer image targets, ties train/val/test. Random with
  all singleton components uses SHA-256(seed|algorithm_version|image_id) order and
  fills targets after pins. Other variants use rarity, size, SHA and image-ID ties.
- Optimize the specified normalized squared-error objective. Multiply its exact
  rational terms by a common positive integer denominator; comparisons stay exact.
  Diagnostic fractions are rounded by the existing six-decimal serializer only
  when emitting JSON and never used for decisions.
- Expand pins to whole components and reject conflicts, unknown image IDs and
  zero-ratio destinations. Repair empty nonzero partitions by the least-cost
  unpinned move that leaves its donor nonempty; ties use group representative ID.
- Up to 20 deterministic improvement passes: scan group IDs ascending and candidate
  destinations train/val/test; accept each strict-improvement move immediately.
  Then scan pair swaps in ascending group-pair order, accepting strict improvements.
  Stop after a pass with no improvement. Exact singleton-random filling does not
  run improvement passes. Pins and nonzero partition membership stay intact.
- Both size and class tolerances are enforced for **every** strategy, even where
  the strategy does not optimize class balance. Choose relaxed tolerances explicitly
  when appropriate; the algorithm never modifies them. Strict rare-class necessary
  failures are distinguished from heuristic failure to find a satisfactory result.
- Record complete per-image assignments, effective component keys, requested/actual
  image and group counts, class distributions, violations, warnings and source hash.
  Failed heuristic previews may contain complete assignments for diagnosis, never
  a READY artifact. Any change to decision/tie rules requires a new algorithm version.

Group-count targets are diagnostic proportional targets; the objective balances
image counts, not the number of unequal-sized groups. The input projection binds
project/version/manifest IDs, class presence, annotation/asset hashes, group values
and policy. It is not a replacement for the release manifest or its verification.

## Run the supplied synthetic preview

From the repository root, with a new output filename:

```powershell
.\.venv\Scripts\python.exe -m visionlabel.split_preview --input tests/fixtures/splitting/source.json --config tests/fixtures/splitting/config.json --output "$env:TEMP\visionlabel-split-preview.json"
```

The fixture contains 16 synthetic image identities, 8 groups and 2 classes. It has
no user images or credentials and is intentionally not an actual release manifest.
Expected counts: train 8, val 4, test 4; each class has 4/2/2 image presence.

The CLI writes exact canonical preview bytes without overwriting existing files
and prints their SHA-256. Exit 0: constraints passed. Exit 2: diagnostic file written
but constraints failed. Exit 1: invalid input/config or IO failure. A changed request
must use explicit changed config; no tolerance relaxation happens automatically.

To compare with another complete preview add both `--compare-input <old-source>`
and `--compare-preview <old-preview>`. The report shows added/removed/moved IDs and
old-test assets or group identities now present in train, even under new image IDs.
The same seed does not freeze a test set across versions. Explicit image pins are
implemented; automatic cross-version pin suggestions remain optional integration work.

## Verification

- Full suite: **104 passed**, including 31 split-engine/CLI cases; Ruff and mypy passed.
- The existing Starlette TestClient HTTPX deprecation warning remains unchanged.
- Four frozen golden assignment vectors and canonical report hashes, plus an
  independent SHA-order oracle for singleton random and a small exhaustive objective
  oracle for one group fixture. This does not claim a global optimum generally.
- Reordering input, changing global RNG state and separate processes with different
  PYTHONHASHSEED values yield identical result bytes.
- Transitive hash/group leakage, unequal group sizes, all strategies, explicit
  missing-group policies, pins, rare classes, disabled partitions, empty repair,
  class presence/empty labels, invalid config and cross-version leakage comparison.
- Developer CLI exercised in subprocesses, including failed constraints and
  overwrite refusal. Package smoke installs the wheel offline and runs this CLI
  outside the repository against the synthetic input files.
- This does not qualify 50,000-image performance or deployment. Pair-swap search
  is quadratic in effective group count; production performance/cancellation and
  background-job integration remain to be verified before release.

## Remaining Phase 4 integration

1. Verify a server-owned RELEASED manifest and every referenced immutable input;
   derive class vectors from its pinned annotation revisions, never from live heads.
2. Add split_runs/split_assignments migrations, authorization/idempotency, background
   jobs, immutable READY triggers, durable manifest publication, crash handling and
   inclusion in verified backup/restore.
3. Add released-version selection and percent/seed/policy/pins controls to the
   desktop, with diagnostics preview, explicit tolerance-change reasons and split
   comparison. Convert user percentages to integer basis points without float drift.
4. Test retry/failure/corruption/concurrency and prove immutable split bytes after
   working data changes. Only then mark the full Phase 4 exit gate complete.

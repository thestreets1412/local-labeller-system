# Synthetic split preview

Algorithm: `vl-split-1`, strategy: `stratified_group`, seed: 42.
This is an algorithm diagnostic, not a production split or an authenticated release.

| Partition | Requested | Images | Effective groups | Class 800 images | Class 801 images |
|---|---:|---:|---:|---:|---:|
| train | 50% | 8 | 4 | 4 | 4 |
| val | 25% | 4 | 2 | 2 | 2 |
| test | 25% | 4 | 2 | 2 | 2 |

All 16 synthetic image identities are assigned once. The 8 groups remain atomic.
No size/class tolerance violations or coverage warnings. Configuration tolerances
are both zero; no relaxation was needed for this fixture.

The complete canonical artifact is `split-preview-v1.json`.
SHA-256: `d692815dafebe6dfbb2116ebb31b38ccb30c4efc02413b2379f1545cd5b33dcb`.
Inputs: `tests/fixtures/splitting/source.json` and `config.json`.

Real dataset integration awaits the release adapter, persistence/jobs and desktop
controls documented in `docs/phase4-plan.md`.

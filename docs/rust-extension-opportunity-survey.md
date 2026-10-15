# Rust/PyO3 opportunity survey — 2026-10-15

Scope: investigation and synthetic component timings only. No application implementation changed.
Earlier image deletion and texture acceleration changes remain in the working tree.

## Workload reported by the user

Approximately 5,400 images, 901 KB each, believed to be 640 x 640, stored on a
hard disk. Complete YOLO predictions contain seven rectangles per image.
That is about 4.9 GB of original data (decimal KB assumption) and 37,800 boxes.
Reported import duration is roughly 30 minutes. Actual image format, disk model,
server data location, cache state and stage timings have not been established.
The survey does not reproduce or attribute that entire duration.

## Import findings

1. **Cumulative progress serialization and database writes** — `service.py:run_import`
   serializes every result accumulated so far and rewrites `jobs.result_json` after
   every image. At 5,400 images this encodes 14,582,700 result entries cumulatively.
   SQLite uses WAL plus synchronous FULL; each progress update has its own write
   transaction. The polling endpoint also returns the full accumulated result.
   First change the report persistence/access pattern: durable individual results
   or bounded batches, cheap counters and paginated/delta reports. Preserve crash
   recovery and per-image outcomes. Simply serializing only once at the end is
   not a sufficient production replacement.

2. **Repeated directory enumeration in YOLO import** — `service.py:ingest` runs
   `source.parent.iterdir()` for every image to detect ambiguous same-stem pairs.
   If all 5,400 images and their 5,400 text files share a directory, that means
   approximately 58.32 million directory-entry examinations. Build an index per
   directory/job and define how concurrent file additions invalidate it. Keep
   case-insensitive ambiguity detection, source-change checks and path safety.
   Rust could implement scanning, but eliminating repeated enumeration is the
   primary improvement and can be implemented in Python.

3. **Repeated image I/O and full raster allocation** — `ingest` reads image bytes,
   writes a staging file, asks the decoder worker to inspect it, then publishes
   the managed asset. `imaging.decode` reads the staging bytes again and WIC opens
   the file, decodes full RGBA pixels and copies them into Python bytes, although
   the import worker returns only width/height. These are logical reads/writes;
   OS caching means they are not all physical HDD transfers. A dedicated
   validation path can avoid returning/materializing an unnecessary Python pixel
   copy, and potentially validate in bounded strips if the codec supports it.
   Do not replace full-image validation with header-only acceptance. WIC already
   does native decoding, so wrapping the same calls in Rust alone has no measured
   speedup. Keep codec isolation in a resource-limited subprocess.

4. **Serialized pipeline and durable commits** — the service has one job worker,
   and import processes images sequentially using one reused decoder process.
   It does not launch one decoder process for every image. YOLO import then runs
   claim/save/release with revision checks and immutable annotation publication.
   HDD flush latency is a plausible contributor, but was not measured here.
   Consider bounded preparation workers and a serialized canonical writer only
   after profiling disk behavior. Increasing concurrency can hurt HDD throughput.
   Keep fsync, durable publication, permission rechecks, fencing and revisions;
   do not gain speed by disabling integrity guarantees.

5. **YOLO text parsing** — Decimal parsing, UUID creation, canonical normalization
   and rectangle validation are CPU work that could be ported. However, matching
   the reported count with synthetic in-memory input took only 2.668 seconds for
   5,400 files x seven boxes. This excludes reading text files and saving results.
   Porting the parser alone is unlikely to explain or solve a 30-minute import.

## Measured component results

Single local diagnostic runs, not repeated statistical benchmarks, except the
three decoder observations. No Rust replacement was benchmarked in this survey.

| Operation | Synthetic input | Observed seconds |
| --- | --- | ---: |
| Cumulative canonical progress reports | 250 images | 0.522 |
| Cumulative canonical progress reports | 500 images | 1.717 |
| Cumulative canonical progress reports | 1,000 images | 6.472 |
| One final canonical report | 1,000 images | 0.022 |
| Repeated sibling enumeration | 1,000 empty image files in one directory | 5.785 |
| Build one index and look up all stems | Same directory, unchanged during experiment | 0.085 |
| YOLO parsing + validation | 1,000 files x 10 boxes | 0.731 |
| YOLO parsing + validation | 5,400 files x 7 boxes, 640 x 640 | 2.668 |
| WIC worker inspection | Synthetic 2048 x 2048 BMP, first call | 0.288 |
| WIC worker inspection | Same BMP, next two calls | 0.048 / 0.049 |
| Export Decimal polygon validation | Convex polygon, 128 vertices | 0.053 |
| Export Decimal polygon validation | Convex polygon, 512 vertices | 0.757 |
| Export Decimal polygon validation | Convex polygon, 1,000 vertices | 2.849 |

The first WIC call includes worker startup. This BMP sample is larger than the
reported dimensions and is not representative proof for the user's unknown
image format. Directory comparison is an algorithm experiment, not a complete
safe indexed importer. Report serialization timings exclude SQLite/flush costs.
Raw results: `docs/verification-artifacts/rust-opportunity-survey.json`.

## Other extension candidates

| Candidate | Rust suitability | Priority and constraints |
| --- | --- | --- |
| Polygon intersection/validation (`domain.py`, `formats.py`) | High: pairwise CPU loops; 1,000-vertex export check measured at 2.849 s | Strongest additional CPU candidate when segmentation is used. Improve algorithm as well; preserve exact decimal/boundary semantics. |
| Canonical serialization (`domain.py:canonical`) | High CPU potential; used in saves, validation, drafts, dirty checks and reports | Fix unnecessary repeated calls first. Native output must match existing bytes, Unicode ordering, half-even rounding and hashes exactly. |
| YOLO export conversion (`formats.py:yolo_labels`) | Medium/high with many objects or polygon vertices | Batch conversion; preserve nine-place quantization, format versions, error diagnostics and golden bytes. Not measured end to end. |
| YOLO parsing (`legacy.py:parse_yolo`) | Medium | Lower priority for seven-box images; bulk API must justify Python/Rust transfer costs. Preserve deterministic IDs and validation errors. |
| Split optimization (`splitting.py:plan_split`) | High for large grouped/stratified workloads: up to 20 pairwise swap passes | Separate diagnostic Phase 4 engine from working-export `split_items`. Preserve deterministic tie-breaking, integer scoring and immutable input gates. Not benchmarked here. |
| Spatial hit testing (`polygon_canvas.py`) | Medium for dense annotations | Consider indexing before Rust. Current seven rectangles per image do not justify prioritizing it. Keep Dear PyGui calls on UI thread. |
| Statistics/QC aggregation (`statistics.py`, `Service.statistics`) | Conditional | Measure JSON/blob reads versus arithmetic first; cached aggregates/query changes may help more. |
| Image validation and thumbnail pipeline (`imaging.py`, `client.py`) | Conditional | Rust useful if it removes copies or combines stages. WIC is already native; preserve no-auto-EXIF-rotation and raw coordinates. |

SHA-256, CRC and codec calls already delegate substantial work to native libraries.
SQLite commits, disk flushes and HTTP orchestration are not good first targets for
a language-only rewrite. Working export ZIP uses ZIP_STORED, so adding a Rust
compression library would not accelerate an existing compression bottleneck.

## Recommended implementation order

1. Record per-stage import timing: read/header/hash, pair lookup, label parse,
   decode, publish, DB commit and progress persistence. Include bytes, counts,
   successes/errors and total wall time; avoid recording confidential filenames
   or annotation contents in performance summaries.
2. Remove repeated directory enumeration and cumulative report rewriting; retain
   durable per-image recovery semantics. Reduce full-report polling.
3. Optimize staging/validation and duplicate handling. Any early duplicate fast
   path must establish trusted asset integrity and preserve deleted-image and
   existing-annotation behavior. Evaluate bounded workers with HDD measurements.
4. Add Rust kernels only for remaining CPU-heavy stages. For this user's import
   workload, prioritize unnecessary work/I/O before the seven-box YOLO parser.
   Polygon geometry is the strongest separately demonstrated Rust candidate.

Extensions can be packaged in the existing optional native wheel. Modules used
by import/export must be installed in the **DataTracking service environment**;
installing only in the desktop environment will not accelerate server jobs.
End users still need no Rust/maturin. Keep a Python fallback, pinned Cargo sources,
license notices and compatibility fixtures. No phase/release/company acceptance
gate is closed by this investigation.

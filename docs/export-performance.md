# Working YOLO export performance and progress — 0.1.2

Authorized 2026-10-16 after a 5,400-image review: Prepare reportedly took about
10 minutes and Save about 30 minutes on the company PC. Those times describe the
user's workload; the company disk and data are not available for local profiling.

Prepare captures saved working data, checks annotations, assigns whole groups to
splits, copies original image bytes into a ZIP and verifies the ZIP. It is more
than a count preview. Save downloads that archive, verifies it, extracts and
verifies every member, then publishes a new client-local dataset directory.

## Changes

| Requirement | Implementation |
| --- | --- |
| EXP-PERF-01 | Fetch matching revision-bound review evidence with one joined query instead of one query per image. The snapshot transaction and confirmation binding remain unchanged. |
| EXP-PERF-02 | Save progress at most twice per second within a stage, plus stage boundaries, instead of one durable database commit per image. Canonical data durability is unchanged. |
| EXP-PERF-03 | Reuse validated YOLO output during ZIP creation and the asset hash already checked against the exact bytes being archived. |
| EXP-PERF-04 | Hash the download while writing it and each extracted file while extracting it. Avoid rereading the completed local ZIP and all extracted files. The server still checks its cached ZIP before sending it. |
| EXP-PERF-05 | Send download responses in 1 MiB chunks instead of 64 KiB, reducing per-chunk HTTP file-read overhead. |
| EXP-UI-01 | Separate Prepare and Save progress bars with stage names, image counts or MiB, and elapsed time. Percentages describe the current stage, not an estimated overall duration. Unknown-length stages say Working. |
| EXP-UI-02 | Workers publish one latest progress value; only the desktop thread updates widgets. Old callbacks cannot overwrite a completed or newer operation. Failed saves can retry the same prepared snapshot. |
| EXP-DIST-01 | Application wheel 0.1.2 is delivered and tracked in rush-wheel. Existing native 0.1.0 remains compatible. |

Migration **0007** adds nullable `jobs.progress_json`. Intermediate progress is
separate from final result JSON, errors and immutable snapshot inputs. Older job
results remain readable. Successful job results include diagnostic stage timings;
publication commit time is outside that timer. Restarted in-flight jobs continue
to fail explicitly, as before; this does not add resume support.

Verification: 308 regression tests passed, including download interruption,
archive/member checksum failures, failed-job history, bounded progress writes and
thread-safe widget updates. Rendered desktop smoke passed real HTTP Prepare/Save,
both completed progress bars and the history screen. The built wheel was installed
into an isolated target and exercised through synthetic import, Prepare and Save
with PATH empty (no Rust toolchain); it loaded migration 0007 successfully.
One existing Starlette TestClient deprecation warning remains. Human mouse/DPI
and the actual company 5,400-image dataset have not been tested in this increment.

Full archive SHA-256, member SHA-256, ZIP CRC, path/manifest validation, per-file
flush/fsync, permissions, immutable sources and final directory publication remain
in place. An interrupted or corrupt download/extraction does not publish the
destination. The standalone `install_archive` entry point still verifies the
complete archive itself; only the client's private download path can reuse its
just-computed streaming checksum.

No new Rust export function is introduced: hashing and ZIP primitives already run
in native libraries. The observed code issues were repeated reads, repeated label
conversion, queries and durable progress writes. The existing Rust extension
continues to accelerate display textures; it is not required for these export gains.
HDD latency, antivirus scanning and the retained per-file durability operations
can still dominate Save on the company PC.

## Measurement

`scripts/benchmark_export.py` creates unique 640 x 640 BMP images (1,228,854 bytes
each) with seven YOLO boxes. Fixture setup is excluded. The service and filesystem
operations are real; HTTP transport is in-process, so this does not measure LAN
throughput or the larger response-chunk improvement.

One local diagnostic run per implementation, 200 images (~246 MB ZIP):

| Step | Before | After |
| --- | ---: | ---: |
| Prepare | 16.540 s | 8.644 s |
| Save | 31.345 s | 23.652 s |

The baseline uses the copied pre-change Python package. These are single runs,
not isolated repeated measurements; filesystem cache and other activity affect
them. They do not predict the company's 5,400-image timings. The measured
implementation predates moving progress metadata into its dedicated column;
that correction changes storage location, not the algorithm or write frequency.
Raw evidence is in `docs/verification-artifacts/export-performance.json`.

```powershell
.\.venv\Scripts\python.exe scripts/benchmark_export.py --count 200 --output dist/export-performance.json
```

## Install

Stop the desktop and DataTracking service and back up server data before the
schema upgrade. In the existing Python 3.12 Windows x64 virtual environment with
runtime dependencies installed, from the repository root:

```powershell
python -m pip install --no-index --no-deps --force-reinstall .\rush-wheel\visionlabel-0.1.2-py3-none-any.whl
```

Install in the **service environment** as well as the desktop environment if they
are separate. Restart the service to apply migration 0007. Existing native 0.1.0
does not need reinstalling. Users need no Rust, maturin or compiler.

Build with `uv build --wheel --out-dir rush-wheel`. Keep the distributed wheel in
Git as explicitly requested by the user; other temporary build and benchmark data
remain outside tracked source. This increment does not close earlier reviewed
release, production packaging or company LAN acceptance gates.

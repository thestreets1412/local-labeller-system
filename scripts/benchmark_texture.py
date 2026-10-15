"""Synthetic conversion benchmark; this is not end-to-end navigation latency."""

import json
import statistics
import time
from array import array

from visionlabel.texture import _native_convert, rgba_texture

if _native_convert is None:
    raise SystemExit("Install the native wheel before benchmarking.")
pixels = bytes(range(256)) * (2048 * 2048 * 4 // 256)
results = {}
for name, convert in (
    ("python", lambda: array("f", (v / 255 for v in pixels))),
    ("rust", lambda: rgba_texture(pixels)),
):
    samples = []
    for _ in range(5):
        started = time.perf_counter()
        result = convert()
        samples.append(time.perf_counter() - started)
        del result
    results[name] = {"median_seconds": statistics.median(samples), "samples_seconds": samples}
results["speedup"] = results["python"]["median_seconds"] / results["rust"]["median_seconds"]
print(json.dumps(results, indent=2))

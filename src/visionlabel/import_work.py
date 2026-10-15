"""Bounded import preparation helpers; canonical writes stay in the service."""

import os
import time
from collections import Counter, defaultdict
from contextlib import contextmanager

from .domain import Problem
from .imaging import IMAGE_EXTENSIONS


class PairIndex:
    def __init__(self):
        self.directories = {}
        self.scans = 0

    @staticmethod
    def stamp(directory):
        stat = directory.stat()
        return stat.st_mtime_ns, stat.st_ctime_ns

    def check(self, source):
        directory = source.parent
        stamp = self.stamp(directory)
        cached = self.directories.get(directory)
        if cached is None or cached[0] != stamp:
            counts: Counter[str] = Counter()
            with os.scandir(directory) as entries:
                for entry in entries:
                    stem, extension = os.path.splitext(entry.name)
                    if extension.lower() in IMAGE_EXTENSIONS and entry.is_file():
                        counts[stem.casefold()] += 1
            self.scans += 1
            if self.stamp(directory) != stamp:
                raise Problem(
                    "SOURCE_CHANGED", "Import directory changed while indexing. Retry after copying finishes."
                )
            cached = stamp, counts
            self.directories[directory] = cached
        if cached[1][source.stem.casefold()] != 1:
            raise Problem(
                "AMBIGUOUS_PAIR",
                "Multiple images share this filename stem. Rename image/label pairs before importing.",
            )


class ImportTimings:
    def __init__(self):
        self.seconds: dict[str, float] = defaultdict(float)
        self.started = time.perf_counter()

    @contextmanager
    def measure(self, stage):
        started = time.perf_counter()
        try:
            yield
        finally:
            self.seconds[stage] += time.perf_counter() - started

    def report(self, index):
        return {
            "elapsed_seconds": round(time.perf_counter() - self.started, 6),
            "stage_seconds": {k: round(v, 6) for k, v in self.seconds.items()},
            "directory_scans": index.scans,
        }

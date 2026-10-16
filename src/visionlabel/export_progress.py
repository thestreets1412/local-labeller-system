"""Bounded, stage-specific export progress; progress writes are not canonical data."""

import time

from .domain import canonical


class JobProgress:
    def __init__(self, srv, job_id):
        self.srv, self.job_id = srv, job_id
        self.phase = None
        self.last_write = float("-inf")
        self.started = self.phase_started = time.monotonic()
        self.timings = {}

    def __call__(self, phase, done, total, unit="images"):
        from .service import now

        current = time.monotonic()
        changed = phase != self.phase
        if changed:
            if self.phase is not None:
                self.timings[self.phase] = round(current - self.phase_started, 6)
            self.phase, self.phase_started = phase, current
        if not changed and current - self.last_write < 0.5:
            return
        self.last_write = current
        with self.srv.db.transaction() as conn:
            conn.exec_driver_sql(
                "UPDATE jobs SET progress_done=?,progress_total=?,progress_json=?,updated_at=? WHERE id=?",
                (
                    done,
                    total,
                    canonical({"progress": {"phase": phase, "unit": unit}}).decode(),
                    now(),
                    self.job_id,
                ),
            )

    def report(self):
        current = time.monotonic()
        return {
            "elapsed_seconds": round(current - self.started, 6),
            "stage_seconds": self.timings | {self.phase: round(current - self.phase_started, 6)},
        }

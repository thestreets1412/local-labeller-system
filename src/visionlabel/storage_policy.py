"""Deterministic, filesystem-independent eviction decisions."""

from datetime import datetime, timedelta


def select_evictions(artifacts, *, max_bytes, max_age_days, now, reserve_bytes=0):
    cutoff = datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(days=max_age_days)
    active = [a for a in artifacts if a["state"] in ("ACTIVE", "EVICTING")]
    retained = sum(a["bytes"] for a in active)
    blocked = sum(a["bytes"] for a in active if a["pinned"] or a["legacy_protected"] or a["in_flight"])
    selected = []
    reclaimed = 0
    for a in sorted(active, key=lambda a: (a["last_access_at"], a["id"])):
        if a["pinned"] or a["legacy_protected"] or a["in_flight"] or a["state"] != "ACTIVE":
            continue
        if (
            retained + reserve_bytes > max_bytes
            or datetime.fromisoformat(a["last_access_at"].replace("Z", "+00:00")) <= cutoff
        ):
            selected.append(a["id"])
            retained -= a["bytes"]
            reclaimed += a["bytes"]
    return {
        "candidate_ids": selected,
        "reclaimable_bytes": reclaimed,
        "retained_bytes": retained,
        "blocked_bytes": blocked,
        "fits_budget": retained + reserve_bytes <= max_bytes,
    }

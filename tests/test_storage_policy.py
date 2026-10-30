from datetime import UTC, datetime, timedelta


def test_policy_preserves_pin_and_accounts_reservation():
    from visionlabel.storage_policy import select_evictions

    now = datetime.now(UTC)
    gib = 1024**3
    entries = [
        {
            "id": name,
            "bytes": gib,
            "last_access_at": (now - timedelta(days=age)).isoformat(),
            "state": "ACTIVE",
            "pinned": pin,
            "legacy_protected": False,
            "in_flight": False,
        }
        for name, age, pin in (("A", 8, False), ("B", 0, False), ("C", 9, True))
    ]
    result = select_evictions(
        entries, max_bytes=3 * gib, max_age_days=7, now=now.isoformat(), reserve_bytes=gib
    )
    assert result["candidate_ids"] == ["A"]
    assert result["retained_bytes"] == 2 * gib
    assert result["fits_budget"]

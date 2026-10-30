from conftest import import_files, project


def test_assets_shared_across_projects_count_once(environment):
    from visionlabel.storage_inventory import scan_storage

    client, srv, root = environment
    a, b = project(client), project(client)
    import_files(client, root, a["id"], 1)
    import_files(client, root, b["id"], 1)
    srv.pool.submit(lambda: None).result()
    report = scan_storage(root, deep=True)
    assert report["complete"], report["warnings"]
    assert len(report["assets"]) == 1
    asset = report["assets"][0]
    assert set(asset["project_ids"]) == {a["id"], b["id"]}
    assert asset["category"] == "active/shared"
    assert report["totals"]["asset_bytes"] == asset["bytes"]
    assert sum(report["project_logical_bytes"].values()) == 2 * asset["bytes"]


def test_old_file_only_orphan_is_reported_not_deleted(environment):
    import os
    import time

    from visionlabel.domain import digest
    from visionlabel.storage_inventory import scan_storage

    _, _, root = environment
    data = b"orphan"
    sha = digest(data)
    path = root / f"managed/assets/sha256/{sha[:2]}/{sha}.png"
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    os.utime(path, (time.time() - 8 * 86400,) * 2)
    report = scan_storage(root, deep=True)
    assert report["assets"][0]["category"] == "file-only orphan candidate"
    assert path.read_bytes() == data
    assert report["totals"]["reclaimable_asset_bytes"] == 0


def test_poisoned_historical_reference_never_opened(environment, monkeypatch):
    from visionlabel.domain import canonical, digest, uid
    from visionlabel.service import now
    from visionlabel.storage_boundary import StorageBoundary
    from visionlabel.storage_inventory import scan_storage

    client, srv, root = environment
    proj = project(client)
    outside = root.parent / "outside.json"
    outside.write_bytes(b"sentinel")
    actor = srv.login("admin", "a-strong-test-password")["user"]["id"]
    # Candidate contains an attacker-controlled reference, never a path authority.
    with srv.db.transaction() as conn:
        conn.exec_driver_sql(
            "INSERT INTO export_candidates VALUES (?,?,?,?,?)",
            (
                uid(),
                proj["id"],
                actor,
                canonical({"asset_path": "../../outside.json"}).decode(),
                now(),
            ),
        )
    accessed = []
    original = StorageBoundary.open_read

    def watched(self, path):
        accessed.append(path)
        return original(self, path)

    monkeypatch.setattr(StorageBoundary, "open_read", watched)
    result = scan_storage(root, deep=True)
    assert not result["complete"]
    assert not any("outside" in p for p in accessed)
    assert digest(outside.read_bytes()) == digest(b"sentinel")

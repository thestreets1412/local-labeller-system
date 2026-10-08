import io
import json
import zipfile
from decimal import Decimal

import pytest
from conftest import claim
from test_formats import CLASSES, rectangle
from test_team import create_user, member
from test_working_export import labeled, start, wait

from visionlabel.class_mapping import model_names, parse_mapping
from visionlabel.domain import Problem, uid
from visionlabel.formats import FORMAT_VERSION, yolo_labels


def mutate(client, method, path, body, key=None, headers=None):
    return client.request(
        method, "/api/v1" + path, json=body, headers={"Idempotency-Key": key or uid(), **(headers or {})}
    )


def test_edge_quantization_golden_and_legacy_behavior():
    source = rectangle(x1=0, y1=0, x2=2, y2=2)
    assert FORMAT_VERSION == "vl-formats-2"
    assert (
        yolo_labels(source, 3, 3, "detection", CLASSES)[0]
        == b"2 0.333333333 0.333333333 0.666666666 0.666666666\n"
    )
    with pytest.raises(Problem):
        yolo_labels(source, 3, 3, "detection", CLASSES, format_version="vl-formats-1")
    assert source["shapes"][0]["x2"] == 2


@pytest.mark.parametrize("width", [3, 7, 641, 10000, 40_000_000])
def test_all_edges_inverse_bound(width):
    for low, high in [
        (0, 1),
        (0, width - 1),
        (1, width),
        (0, width),
        (Decimal("0.123456"), Decimal(width) - Decimal("0.654321")),
    ]:
        source = rectangle(x1=low, x2=high, y1=0, y2=1)
        data, _ = yolo_labels(source, width, 1, "detection", CLASSES)
        _, cx, cy, w, h = data.decode().split()
        cx, cy, w, h = map(Decimal, (cx, cy, w, h))
        left, right = cx - w / 2, cx + w / 2
        assert 0 <= left < right <= 1
        assert 0 <= cy - h / 2 < cy + h / 2 <= 1
        assert abs(left * width - low) <= Decimal("0.00000000125") * width
        assert abs(right * width - high) <= Decimal("0.00000000125") * width
    with pytest.raises(Problem, match="quantization"):
        yolo_labels(rectangle(x1=0, x2=Decimal("0.000001"), y1=0, y2=1), 3000, 1, "detection", CLASSES)


@pytest.mark.parametrize(
    "text",
    [
        "names: [part, defect]\ntrain: images/train",
        'names:\n  0: part\n  1: "defect"\n',
        "names:\n- part\n- defect\n",
        '{"names": ["part", "defect"]}',
    ],
)
def test_model_names_common_data_only_formats(text):
    assert model_names(text) == {0: "part", 1: "defect"}


@pytest.mark.parametrize(
    "text",
    [
        "names:\n  0: a\n  0: b",
        "names: [a, a]",
        "names:\n  1: a",
        "names: !!python/object:evil {}",
        "names: []",
    ],
)
def test_model_names_reject_ambiguous_input(text):
    with pytest.raises(Problem):
        model_names(text)


@pytest.mark.parametrize(
    "text",
    ['{"names":{"0":"a","0":"b"}}', 'names: {0: "a", 0: "b"}', "names: [a]\nnames: [b]", "names: {**evil}"],
)
def test_model_names_duplicate_fields_and_expansion_rejected(text):
    with pytest.raises(Problem):
        model_names(text)


def test_classification_mapping_keeps_schema_and_consumer_indices(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, "classification", count=3)
    entries = proj["schema"]["entries"]
    mapping = {entries[0]["class_id"]: 1, entries[1]["class_id"]: 0, entries[2]["class_id"]: 2}
    job = wait(client, start(client, proj, class_mapping=mapping).json()["job_id"])
    assert job["state"] == "succeeded", job
    bundle = zipfile.ZipFile(io.BytesIO(client.get(f"/api/v1/working-exports/{job['id']}/download").content))
    folder = json.loads(bundle.read("class_mapping.json"))["classification_folders"][0]
    assert folder["schema_export_index"] == 0
    assert folder["model_export_index"] == 1
    assert folder["consumer_order"] == 0
    assert folder["folder_name"] == "0001_class_0"


def test_manager_keeps_editor_locked_until_operation_finishes(monkeypatch):
    from types import SimpleNamespace

    from visionlabel import project_ui

    calls, configs, messages = [], {}, []
    monkeypatch.setattr(project_ui.dpg, "configure_item", lambda tag, **kw: configs.update({tag: kw}))
    monkeypatch.setattr(project_ui.dpg, "set_value", lambda tag, value: messages.append(value))
    app = SimpleNamespace(busy=False, saving=False, client=object(), submit=lambda *args: calls.append(args))
    panel = project_ui.ProjectPanel(app)
    completed = []
    panel.run(lambda: "result", completed.append)
    assert app.busy and panel.busy
    assert not configs["pm_remap_mapping"]["enabled"]
    panel.run(lambda: "overlap", completed.append)
    assert len(calls) == 1
    calls[0][1](calls[0][0]())
    assert completed == ["result"] and not app.busy and not panel.busy
    panel.run(lambda: None, completed.append)
    calls[1][2](Problem("DISCONNECTED", "Connection lost"))
    assert not app.busy and not panel.busy
    assert messages[-1] == "Connection lost"


def test_export_mapping_is_explicit_and_frozen(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=3)
    entries = proj["schema"]["entries"]
    mapping = {e["class_id"]: (1 if i == 0 else 0 if i == 1 else i) for i, e in enumerate(entries)}
    mapped = wait(client, start(client, proj, class_mapping=mapping).json()["job_id"])
    assert mapped["state"] == "succeeded", mapped
    job_id = mapped["id"]
    raw = client.get(f"/api/v1/working-exports/{job_id}/download").content
    bundle = zipfile.ZipFile(io.BytesIO(raw))
    manifest = json.loads(bundle.read("manifest.json"))
    assert manifest["format_version"] == "vl-formats-2"
    assert all(
        bundle.read(f"labels/{i['partition']}/{i['image_id']}.txt").startswith(b"1 ")
        for i in manifest["items"]
    )
    classes = json.loads(bundle.read("class_mapping.json"))["classes"]
    assert next(c for c in classes if c["class_id"] == entries[0]["class_id"])["schema_export_index"] == 0
    assert client.get(f"/api/v1/projects/{proj['id']}").json()["schema"] == proj["schema"]
    assert start(client, proj, class_mapping={entries[0]["class_id"]: 0}).status_code == 422
    assert start(client, proj, class_mapping={**mapping, entries[0]["class_id"]: True}).status_code == 422
    assert (
        parse_mapping("0=defect\n1=part\n2=background", entries, complete=True)[1] == entries[0]["class_id"]
    )
    history = client.get(f"/api/v1/projects/{proj['id']}/versions").json()
    assert history["working"]["images"] == 3
    assert history["schemas"][0]["number"] == 1
    assert history["exports"][0]["options"]["class_mapping"] == mapping
    assert not history["exports"][0]["approved_release"]


def test_project_folders_archive_templates_permissions_and_cas(environment):
    client, srv, root = environment
    proj, images = labeled(client, root, count=1)
    folder = mutate(client, "POST", "/project-folders", {"name": "Factory 1"}).json()
    child = mutate(
        client, "POST", "/project-folders", {"name": "Machine A", "parent_id": folder["id"]}
    ).json()
    assert (
        mutate(
            client,
            "PUT",
            f"/project-folders/{folder['id']}",
            {"name": "Factory", "parent_id": child["id"], "expected_revision": 1},
        ).status_code
        == 422
    )
    body = {
        "expected_project_revision": 1,
        "name": "Detect Top Assy",
        "description": "โรงงาน",
        "folder_id": child["id"],
        "archived": False,
    }
    key = uid()
    response = mutate(client, "PATCH", f"/projects/{proj['id']}", body, key)
    assert response.status_code == 200, response.text
    assert mutate(client, "PATCH", f"/projects/{proj['id']}", body, key).json() == response.json()
    assert mutate(client, "PATCH", f"/projects/{proj['id']}", body).status_code == 409
    assert (
        mutate(
            client,
            "PUT",
            f"/project-folders/{child['id']}",
            {"name": "Machine A", "expected_revision": 1, "delete": True},
        ).status_code
        == 409
    )
    template = mutate(client, "POST", f"/projects/{proj['id']}/class-templates", {"name": "Detection base"})
    assert template.status_code == 200
    assert template.json()["initial_classes"] == ["part", "defect", "background"]
    outsider = create_user(client)
    auth = {"Authorization": "Bearer " + srv.login("junior", "a-long-user-password")["token"]}
    assert client.get("/api/v1/project-folders", headers=auth).json()["items"] == []
    assert client.get("/api/v1/class-templates", headers=auth).json()["items"] == []
    assert member(client, response.json(), outsider, "viewer", revision=2).status_code == 200
    assert {f["id"] for f in client.get("/api/v1/project-folders", headers=auth).json()["items"]} == {
        folder["id"],
        child["id"],
    }
    assert (
        mutate(
            client, "PATCH", f"/projects/{proj['id']}", body | {"expected_project_revision": 3}, headers=auth
        ).status_code
        == 403
    )
    archived = mutate(
        client, "PATCH", f"/projects/{proj['id']}", body | {"expected_project_revision": 3, "archived": True}
    )
    assert archived.status_code == 200
    assert client.get("/api/v1/projects").json()["items"] == []
    assert client.get("/api/v1/projects?include_archived=true").json()["items"][0]["archived"]
    assert (
        mutate(
            client, "POST", f"/images/{images[0]['id']}/claim", {"mode": "edit", "client_instance_id": uid()}
        ).status_code
        == 409
    )
    assert client.get(f"/api/v1/images/{images[0]['id']}/annotation").json()["revision"] == 1
    assert (
        mutate(
            client, "PATCH", f"/projects/{proj['id']}", body | {"expected_project_revision": 4}
        ).status_code
        == 200
    )
    empty = mutate(client, "POST", "/project-folders", {"name": "Empty"}).json()
    delete_key = uid()
    delete_body = {"name": "Empty", "expected_revision": 1, "delete": True}
    for _ in range(2):
        assert (
            mutate(client, "PUT", f"/project-folders/{empty['id']}", delete_body, delete_key).status_code
            == 200
        )


@pytest.mark.parametrize("task", ["detection", "segmentation", "classification"])
def test_remap_preview_leases_revisions_and_history(environment, task):
    client, srv, root = environment
    proj, images = labeled(client, root, task, count=3)
    iid = images[0]["id"]
    entries = proj["schema"]["entries"]
    mapping = {entries[0]["class_id"]: entries[1]["class_id"]}
    export = wait(client, start(client, proj).json()["job_id"])
    archive_before = client.get(f"/api/v1/working-exports/{export['id']}/download").content
    original = client.get(f"/api/v1/images/{iid}/annotation").json()
    preview = mutate(
        client, "POST", f"/projects/{proj['id']}/remap-preview", {"image_ids": [iid], "mapping": mapping}
    )
    assert preview.status_code == 200, preview.text
    item = preview.json()["items"][0]
    assert item["changed_labels"] == 1
    assert client.get(f"/api/v1/images/{iid}/annotation").json() == original
    body = {
        k: item[k]
        for k in ("expected_revision", "expected_state_revision", "annotation_sha256", "class_schema_id")
    } | {"mapping": mapping}
    assert mutate(client, "POST", f"/images/{iid}/remap", body).status_code != 200
    lease = claim(client, iid)
    key = uid()
    response = mutate(client, "POST", f"/images/{iid}/remap", body, key, lease)
    assert response.status_code == 200, response.text
    assert response.json()["revision"] == 2
    assert mutate(client, "POST", f"/images/{iid}/remap", body, key, lease).json() == response.json()
    assert mutate(client, "POST", f"/images/{iid}/remap", body, headers=lease).status_code == 409
    head = client.get(f"/api/v1/images/{iid}/annotation").json()
    if task == "classification":
        assert head["annotation"]["image_labels"] == [entries[1]["class_id"]]
    else:
        assert head["annotation"]["shapes"][0]["class_id"] == entries[1]["class_id"]
        assert head["annotation"]["shapes"][0]["id"] == original["annotation"]["shapes"][0]["id"]
    assert client.get(f"/api/v1/working-exports/{export['id']}/download").content == archive_before
    with srv.db.engine.connect() as conn:
        old = conn.exec_driver_sql(
            "SELECT blob_path,sha256 FROM annotation_revisions WHERE image_id=? AND revision=1", (iid,)
        ).one()
        audits = (
            conn.exec_driver_sql(
                "SELECT detail_json FROM audit_events WHERE entity_id=? AND action='annotation.saved'", (iid,)
            )
            .scalars()
            .all()
        )
    assert srv.blobs.json(old[0], old[1]) == original["annotation"]
    assert any(json.loads(a).get("remap", {}).get("mapping") == mapping for a in audits)

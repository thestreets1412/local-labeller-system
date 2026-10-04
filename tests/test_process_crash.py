import json
import os
import subprocess
import sys

import pytest
from conftest import claim, import_files, project, save_body

from visionlabel.domain import uid
from visionlabel.service import Service


@pytest.mark.parametrize("boundary", ["after_publish", "after_commit"])
def test_abrupt_process_exit_keeps_committed_head(environment, tmp_path, boundary):
    client, service, root = environment
    proj = project(client)
    image = import_files(client, root, proj["id"])[0]
    claim(client, image["id"])
    service.close()
    key = uid()
    body = save_body(proj)
    payload = {"root": str(root), "body": body, "image_id": image["id"], "key": key, "boundary": boundary}
    inputfile = tmp_path / "crash-input.json"
    inputfile.write_text(json.dumps(payload), encoding="utf-8")
    code = """
import json,os,sys
from pathlib import Path
from visionlabel.service import Service
from visionlabel.domain import uid
p=json.loads(Path(sys.argv[1]).read_text())
s=Service(Path(p['root']))
u=s.authenticate(s.login('admin','a-strong-test-password')['token'])
c=s.claim(u,p['image_id'],{'mode':'edit','client_instance_id':uid()},uid(),uid())
h={'id':c['claim_id'],'token':c['claim_token'],'generation':c['generation']}
s.fault=lambda point:os._exit(73) if point==p['boundary'] else None
s.save(u,p['image_id'],p['body'],h,p['key'],uid())
"""
    result = subprocess.run(
        [sys.executable, "-c", code, str(inputfile)],
        timeout=30,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    assert result.returncode == 73
    restarted = Service(root)
    client.app.state.service = restarted
    user = restarted.authenticate(restarted.login("admin", "a-strong-test-password")["token"])
    loaded = restarted.annotation(user, image["id"])
    assert loaded["revision"] == (1 if boundary == "after_commit" else 0)
    if boundary == "after_commit":
        replay = restarted.save(user, image["id"], body, {}, key, uid())
        assert replay["annotation_sha256"] == loaded["annotation_sha256"]
    with restarted.db.engine.connect() as conn:
        assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
        assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []

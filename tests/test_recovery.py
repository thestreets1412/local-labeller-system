import json

from visionlabel.client import LocalStore, protect
from visionlabel.domain import uid


def test_private_draft_atomic_roundtrip(tmp_path):
    image_id = uid()
    store = LocalStore("http://127.0.0.1:8765", uid(), tmp_path)
    content = {
        "content": {"shapes": [], "verified_empty": True, "image_labels": []},
        "base_revision": 7,
        "base_hash": "a" * 64,
    }
    store.save_draft(image_id, content)
    assert store.load_draft(image_id) == content
    assert b"base_revision" not in store.draft_path(image_id).read_bytes()
    assert json.loads(protect(store.draft_path(image_id).read_bytes(), True)) == content
    assert not store.draft_path(image_id).with_suffix(".tmp").exists()
    store.remove_draft(image_id)
    assert store.load_draft(image_id) is None


def test_store_scopes_do_not_share_drafts(tmp_path):
    image_id, user_id = uid(), uid()
    first = LocalStore("http://127.0.0.1:8765", user_id, tmp_path)
    first.save_draft(image_id, {"content": "private"})
    assert LocalStore("http://127.0.0.1:8766", user_id, tmp_path).load_draft(image_id) is None
    assert LocalStore("http://127.0.0.1:8765", uid(), tmp_path).load_draft(image_id) is None

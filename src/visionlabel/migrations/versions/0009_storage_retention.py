"""Separate removable export artifacts from immutable export evidence."""

from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE export_receipts (id TEXT PRIMARY KEY, blob_path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    op.execute(
        "CREATE TABLE export_artifacts (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), cache_key TEXT NOT NULL, path TEXT NOT NULL UNIQUE, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, receipt_id TEXT NOT NULL REFERENCES export_receipts(id), state TEXT NOT NULL, pinned INTEGER NOT NULL DEFAULT 0, legacy_protected INTEGER NOT NULL DEFAULT 0, last_access_at TEXT NOT NULL)"
    )
    op.execute("CREATE INDEX export_artifacts_key ON export_artifacts(cache_key,state)")
    op.execute(
        "CREATE TABLE export_job_artifacts (job_id TEXT PRIMARY KEY REFERENCES jobs(id), artifact_id TEXT NOT NULL REFERENCES export_artifacts(id))"
    )
    op.execute(
        "CREATE TABLE storage_policy (id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL, max_bytes INTEGER NOT NULL, max_age_days INTEGER NOT NULL, automatic_enabled INTEGER NOT NULL)"
    )
    op.execute("INSERT INTO storage_policy VALUES (1,1,4294967296,7,0)")
    op.execute(
        "CREATE TABLE storage_cleanup_operations (id TEXT PRIMARY KEY, actor_id TEXT, root_identity TEXT NOT NULL, generation INTEGER NOT NULL, expires_at TEXT NOT NULL, entries_json TEXT NOT NULL, result_json TEXT)"
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER immutable_export_receipts_{action.lower()} BEFORE {action} ON export_receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END"
        )


def downgrade():
    raise RuntimeError("Storage receipts are retained history; restore a verified backup to downgrade.")

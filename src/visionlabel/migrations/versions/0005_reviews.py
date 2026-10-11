"""Revision-bound working reviews and review settings."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE projects ADD COLUMN allow_self_review INTEGER NOT NULL DEFAULT 0 CHECK(allow_self_review IN (0,1))"
    )
    op.execute(
        "ALTER TABLE task_claims ADD COLUMN mode TEXT NOT NULL DEFAULT 'edit' CHECK(mode IN ('edit','review'))"
    )
    op.execute(
        "CREATE TABLE working_reviews (id TEXT PRIMARY KEY, image_id TEXT NOT NULL, annotation_revision INTEGER NOT NULL, annotation_sha256 TEXT NOT NULL, schema_id TEXT NOT NULL REFERENCES class_schemas(id), state_revision INTEGER NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('accept','reject')), comment TEXT NOT NULL, reviewer_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, FOREIGN KEY(image_id,annotation_revision) REFERENCES annotation_revisions(image_id,revision), UNIQUE(image_id,state_revision))"
    )
    op.execute(
        "CREATE TABLE export_candidates (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), user_id TEXT NOT NULL REFERENCES users(id), snapshot_json TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    for operation in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER immutable_working_reviews_{operation.lower()} BEFORE {operation} ON working_reviews BEGIN SELECT RAISE(ABORT,'immutable record'); END"
        )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade.")

"""Immutable working dataset checkpoints and optimistic dataset operations."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE projects ADD COLUMN dataset_generation INTEGER NOT NULL DEFAULT 0")
    op.execute(
        "CREATE TABLE dataset_checkpoints (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), sequence INTEGER NOT NULL, label TEXT NOT NULL, message TEXT NOT NULL, parent_id TEXT REFERENCES dataset_checkpoints(id), restored_from_id TEXT REFERENCES dataset_checkpoints(id), blob_path TEXT NOT NULL, sha256 TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, UNIQUE(project_id,sequence), UNIQUE(project_id,label))"
    )
    op.execute(
        "CREATE TABLE dataset_operations (id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id), created_by TEXT NOT NULL REFERENCES users(id), kind TEXT NOT NULL, generation INTEGER NOT NULL, blob_path TEXT NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL, expires_at TEXT NOT NULL, result_json TEXT, cancelled INTEGER NOT NULL DEFAULT 0)"
    )
    for action in ("UPDATE", "DELETE"):
        op.execute(
            f"CREATE TRIGGER immutable_dataset_checkpoints_{action.lower()} BEFORE {action} ON dataset_checkpoints BEGIN SELECT RAISE(ABORT,'immutable record'); END"
        )
    # Cover writes at their owning tables, including import/remap and future APIs.
    for table, owner in (
        ("images", "NEW.project_id"),
        ("annotation_heads", "(SELECT project_id FROM images WHERE id=NEW.image_id)"),
    ):
        for action in ("INSERT", "UPDATE"):
            op.execute(
                f"CREATE TRIGGER dataset_generation_{table}_{action.lower()} AFTER {action} ON {table} BEGIN UPDATE projects SET dataset_generation=dataset_generation+1 WHERE id={owner}; END"
            )
    op.execute(
        "CREATE TRIGGER dataset_generation_schema AFTER UPDATE OF active_schema_id ON projects WHEN OLD.active_schema_id IS NOT NEW.active_schema_id BEGIN UPDATE projects SET dataset_generation=dataset_generation+1 WHERE id=NEW.id; END"
    )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade.")

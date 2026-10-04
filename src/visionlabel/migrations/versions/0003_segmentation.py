"""Enable the segmentation task without rewriting existing project identities."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    # Database.migrate holds an explicit transaction with foreign keys temporarily
    # off on this connection only. Referencing table names never change.
    op.execute(
        "CREATE TABLE projects_new (id TEXT PRIMARY KEY, slug TEXT NOT NULL UNIQUE, name TEXT NOT NULL, task_type TEXT NOT NULL CHECK(task_type IN ('detection','classification','segmentation')), active_schema_id TEXT REFERENCES class_schemas(id), project_revision INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL, created_by TEXT NOT NULL REFERENCES users(id))"
    )
    op.execute("INSERT INTO projects_new SELECT * FROM projects")
    op.execute("DROP TABLE projects")
    op.execute("ALTER TABLE projects_new RENAME TO projects")


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported. Restore a verified backup instead.")

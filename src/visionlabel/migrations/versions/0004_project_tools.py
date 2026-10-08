"""Project organization and reusable local class templates."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE project_folders (id TEXT PRIMARY KEY, name TEXT NOT NULL, parent_id TEXT REFERENCES project_folders(id), owner_id TEXT NOT NULL REFERENCES users(id), revision INTEGER NOT NULL DEFAULT 1)"
    )
    op.execute("ALTER TABLE projects ADD COLUMN description TEXT NOT NULL DEFAULT ''")
    op.execute("ALTER TABLE projects ADD COLUMN archived INTEGER NOT NULL DEFAULT 0 CHECK(archived IN (0,1))")
    op.execute("ALTER TABLE projects ADD COLUMN folder_id TEXT REFERENCES project_folders(id)")
    op.execute(
        "CREATE TABLE class_templates (id TEXT PRIMARY KEY, owner_id TEXT NOT NULL REFERENCES users(id), name TEXT NOT NULL, task_type TEXT NOT NULL, classes_json TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    op.execute("CREATE INDEX project_folder ON projects(folder_id)")


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade.")

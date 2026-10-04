"""Optimistic revisions for account administration."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE users ADD COLUMN user_revision INTEGER NOT NULL DEFAULT 1 CHECK(user_revision>0)")


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported. Restore a verified backup instead.")

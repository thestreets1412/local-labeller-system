"""Keep stage progress separate from completed job results and immutable snapshots."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE jobs ADD COLUMN progress_json TEXT")


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade.")

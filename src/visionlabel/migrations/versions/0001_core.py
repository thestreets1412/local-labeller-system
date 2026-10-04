"""Phase 1 immutable annotation foundation."""

from alembic import op

from visionlabel.database import SCHEMA

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    for statement in SCHEMA:
        op.execute(statement)


def downgrade():
    raise RuntimeError("Destructive downgrade is unsupported. Restore a verified backup instead.")

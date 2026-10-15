"""Persist import outcomes independently instead of rewriting the growing report."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE import_results (job_id TEXT NOT NULL REFERENCES jobs(id), ordinal INTEGER NOT NULL CHECK(ordinal>0), result_json TEXT NOT NULL, PRIMARY KEY(job_id,ordinal))"
    )


def downgrade():
    raise RuntimeError("Restore a verified backup instead of destructive downgrade.")

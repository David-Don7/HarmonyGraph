"""Research v2 annotation context and unresolved judgments.

Revision ID: 0004
Revises: 0003
"""

from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("annotators", sa.Column("qualifications", sa.Text(), server_default=""))
    op.add_column("benchmark_queries", sa.Column("protocol", sa.JSON(), server_default="{}"))
    with op.batch_alter_table("relevance_judgments") as batch:
        batch.alter_column("relevance", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Do not silently convert unresolved ratings into irrelevant judgments.
    bind = op.get_bind()
    if bind.scalar(sa.text("SELECT count(*) FROM relevance_judgments WHERE relevance IS NULL")):
        raise RuntimeError("Export and resolve nullable judgments before downgrading")
    with op.batch_alter_table("relevance_judgments") as batch:
        batch.alter_column("relevance", existing_type=sa.Integer(), nullable=False)
    op.drop_column("benchmark_queries", "protocol")
    op.drop_column("annotators", "qualifications")

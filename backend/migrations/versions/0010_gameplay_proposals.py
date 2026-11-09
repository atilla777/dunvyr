"""Owner-scoped proposal collections and independent idempotency receipts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gameplay_proposal_collections",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("actor_id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_proposal_version"),
    )
    op.create_table(
        "gameplay_proposal_receipts",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("actor_id", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gameplay_proposal_receipts")
    op.drop_table("gameplay_proposal_collections")

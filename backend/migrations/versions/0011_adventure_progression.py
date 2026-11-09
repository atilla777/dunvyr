"""Mutable adventure progression, separate from immutable pinned snapshots."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adventures_progression",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_table(
        "gameplay_check_audits",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("content", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("gameplay_check_audits")
    op.drop_table("adventures_progression")

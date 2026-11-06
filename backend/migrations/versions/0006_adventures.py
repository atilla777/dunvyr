"""Own immutable adventure snapshots and their resources.

Revision ID: 0006
Revises: 0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adventures_snapshots",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("adventure_id", sa.Text(), nullable=False),
        sa.Column("fingerprint", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
    )
    op.create_table(
        "adventures_resources",
        sa.Column("campaign_id", sa.Text(), nullable=False),
        sa.Column("resource_id", sa.Text(), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(["campaign_id"], ["adventures_snapshots.campaign_id"]),
        sa.PrimaryKeyConstraint("campaign_id", "resource_id"),
    )


def downgrade() -> None:
    op.drop_table("adventures_resources")
    op.drop_table("adventures_snapshots")

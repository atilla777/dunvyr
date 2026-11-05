"""Business migration 0004: unique member nickname within a campaign.

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05

SQLite cannot add a table constraint in place, so Alembic rebuilds
``campaigns_members`` and re-creates the unique constraint on the new table.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

NICKNAME_CONSTRAINT = "uq_campaigns_members_campaign_id_nickname"


def upgrade() -> None:
    with op.batch_alter_table("campaigns_members") as batch_op:
        batch_op.create_unique_constraint(
            NICKNAME_CONSTRAINT,
            ["campaign_id", "nickname"],
        )


def downgrade() -> None:
    with op.batch_alter_table("campaigns_members") as batch_op:
        batch_op.drop_constraint(NICKNAME_CONSTRAINT, type_="unique")

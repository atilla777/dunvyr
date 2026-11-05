"""Business migration 0003: campaigns, memberships and invitation hashes.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns_campaigns",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("max_seats", sa.Integer(), nullable=False),
        sa.Column("organizer_id", sa.Text(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("invitation_token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("invitation_revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "organizer_id",
            "idempotency_key",
            name="uq_campaigns_campaigns_organizer_idempotency",
        ),
    )
    op.create_index(
        "ix_campaigns_campaigns_organizer_id",
        "campaigns_campaigns",
        ["organizer_id"],
    )
    op.create_table(
        "campaigns_members",
        sa.Column(
            "campaign_id",
            sa.Text(),
            sa.ForeignKey("campaigns_campaigns.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("guest_id", sa.Text(), nullable=False),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("joined_at", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("campaign_id", "guest_id", name="pk_campaigns_members"),
    )
    op.create_index(
        "ix_campaigns_members_campaign_id",
        "campaigns_members",
        ["campaign_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_campaigns_members_campaign_id", table_name="campaigns_members")
    op.drop_table("campaigns_members")
    op.drop_index("ix_campaigns_campaigns_organizer_id", table_name="campaigns_campaigns")
    op.drop_table("campaigns_campaigns")

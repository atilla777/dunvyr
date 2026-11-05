"""Business migration 0005: communication chat event stream.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-05

One table stores both chat messages and member_joined facts so the per-campaign
sequence, snapshot and live delivery share a single chronological stream.
Campaign identifiers are opaque text values: communication owns no campaigns
tables and declares no cross-context foreign key.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "communication_events",
        sa.Column("campaign_id", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Text(), nullable=False),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.Text(), nullable=False),
        sa.Column("message_id", sa.Text(), nullable=True),
        sa.Column("author_id", sa.Text(), nullable=True),
        sa.Column("author_nickname", sa.Text(), nullable=True),
        sa.Column("client_message_id", sa.Text(), nullable=True),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("member_guest_id", sa.Text(), nullable=True),
        sa.Column("member_nickname", sa.Text(), nullable=True),
        sa.Column("member_role", sa.Text(), nullable=True),
        sa.Column("member_joined_at", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("campaign_id", "sequence", name="pk_communication_events"),
        sa.UniqueConstraint("event_id", name="uq_communication_events_event_id"),
        sa.UniqueConstraint(
            "campaign_id",
            "client_message_id",
            name="uq_communication_events_campaign_client_message",
        ),
        sa.UniqueConstraint(
            "campaign_id",
            "member_guest_id",
            name="uq_communication_events_campaign_member",
        ),
    )
    op.create_index(
        "ix_communication_events_campaign_id",
        "communication_events",
        ["campaign_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_communication_events_campaign_id", table_name="communication_events")
    op.drop_table("communication_events")

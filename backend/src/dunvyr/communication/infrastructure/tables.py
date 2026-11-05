"""SQLAlchemy Core tables owned by the communication bounded context.

Every table carries the ``communication_`` prefix. Campaigns and identity rows
are referenced by opaque UUID text values only, without cross-context foreign
keys: communication never reads or writes foreign tables directly.
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

communication_events = sa.Table(
    "communication_events",
    metadata,
    sa.Column("campaign_id", sa.Text(), nullable=False, index=True),
    sa.Column("sequence", sa.Integer(), nullable=False),
    sa.Column("event_id", sa.Text(), nullable=False, unique=True),
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

__all__ = ["communication_events", "metadata"]

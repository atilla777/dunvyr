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
    sa.Column("game_session_revision", sa.Integer()),
    sa.Column("game_session_state", sa.Text()),
    sa.Column("queue_version", sa.Integer()),
    sa.Column("queue_state", sa.Text()),
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

communication_narrations = sa.Table(
    "communication_narrations",
    metadata,
    sa.Column("result_event_id", sa.Text(), primary_key=True),
    sa.Column("campaign_id", sa.Text(), nullable=False),
    sa.Column("context", sa.Text(), nullable=False),
    sa.Column("state", sa.Text(), nullable=False),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("attempt_token", sa.Text()),
    sa.Column("lease_until", sa.Float()),
    sa.Column("updated_at", sa.Float(), nullable=False),
    sa.Column("text", sa.Text()),
    sa.Column("error", sa.Text()),
)

communication_narration_starts = sa.Table(
    "communication_narration_starts",
    metadata,
    sa.Column("token", sa.Text(), primary_key=True),
    sa.Column("campaign_id", sa.Text(), nullable=False),
    sa.Column("started_at", sa.Float(), nullable=False),
)

communication_narration_retries = sa.Table(
    "communication_narration_retries",
    metadata,
    sa.Column("campaign_id", sa.Text(), primary_key=True),
    sa.Column("actor_id", sa.Text(), primary_key=True),
    sa.Column("key", sa.Text(), primary_key=True),
    sa.Column("result_event_id", sa.Text(), nullable=False),
    sa.Column("expected_revision", sa.Integer(), nullable=False),
    sa.Column("created_at", sa.Float(), nullable=False),
)

sa.Index(
    "uq_communication_game_session_revision",
    communication_events.c.campaign_id,
    communication_events.c.game_session_revision,
    unique=True,
)

sa.Index(
    "uq_communication_queue_version",
    communication_events.c.campaign_id,
    communication_events.c.queue_version,
    unique=True,
)

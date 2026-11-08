"""SQLAlchemy Core tables owned by the campaigns bounded context.

Every table carries the ``campaigns_`` prefix, which denotes ownership: other
contexts must never read or write these tables directly. Identity guests are
referenced by opaque UUID text values only, without a cross-context foreign key.
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

campaigns = sa.Table(
    "campaigns_campaigns",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("name", sa.Text(), nullable=False),
    sa.Column("max_seats", sa.Integer(), nullable=False),
    sa.Column("organizer_id", sa.Text(), nullable=False, index=True),
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

members = sa.Table(
    "campaigns_members",
    metadata,
    sa.Column(
        "campaign_id",
        sa.Text(),
        sa.ForeignKey("campaigns_campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("guest_id", sa.Text(), nullable=False),
    sa.Column("nickname", sa.Text(), nullable=False),
    sa.Column("role", sa.Text(), nullable=False),
    sa.Column("joined_at", sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint("campaign_id", "guest_id", name="pk_campaigns_members"),
    sa.UniqueConstraint(
        "campaign_id",
        "nickname",
        name="uq_campaigns_members_campaign_id_nickname",
    ),
)

__all__ = ["campaigns", "members", "metadata"]

game_sessions = sa.Table(
    "campaigns_game_sessions",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("campaign_id", sa.Text(), sa.ForeignKey("campaigns_campaigns.id"), nullable=False),
    sa.Column("status", sa.Text(), nullable=False),
    sa.Column("started_at", sa.Text(), nullable=False),
    sa.Column("ended_at", sa.Text()),
    sa.CheckConstraint("status IN ('running', 'paused', 'ended')", name="ck_game_session_status"),
)
sa.Index(
    "uq_game_session_active",
    game_sessions.c.campaign_id,
    unique=True,
    sqlite_where=game_sessions.c.status.in_(["running", "paused"]),
)

session_state = sa.Table(
    "campaigns_session_state",
    metadata,
    sa.Column("campaign_id", sa.Text(), sa.ForeignKey("campaigns_campaigns.id"), primary_key=True),
    sa.Column("revision", sa.Integer(), nullable=False),
    sa.Column("session_id", sa.Text(), sa.ForeignKey("campaigns_game_sessions.id")),
    sa.CheckConstraint("revision >= 0", name="ck_session_revision"),
)
session_receipts = sa.Table(
    "campaigns_session_receipts",
    metadata,
    sa.Column("campaign_id", sa.Text(), sa.ForeignKey("campaigns_campaigns.id"), primary_key=True),
    sa.Column("actor_id", sa.Text(), primary_key=True),
    sa.Column("key", sa.Text(), primary_key=True),
    sa.Column("payload", sa.Text(), nullable=False),
    sa.Column("response", sa.Text(), nullable=False),
)

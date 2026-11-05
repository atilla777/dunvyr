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
)

__all__ = ["campaigns", "members", "metadata"]

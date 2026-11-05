"""SQLAlchemy Core tables owned by the identity bounded context.

Every table carries the ``identity_`` prefix, which denotes ownership: other
contexts must never read or write these tables directly.
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

guests = sa.Table(
    "identity_guests",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("nickname", sa.Text(), nullable=False),
    sa.Column("created_at", sa.Text(), nullable=False),
)

sessions = sa.Table(
    "identity_sessions",
    metadata,
    sa.Column("id", sa.Text(), primary_key=True),
    sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
    sa.Column(
        "guest_id",
        sa.Text(),
        sa.ForeignKey("identity_guests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    sa.Column("created_at", sa.Text(), nullable=False),
    sa.Column("expires_at", sa.Text(), nullable=False),
)

__all__ = ["guests", "metadata", "sessions"]

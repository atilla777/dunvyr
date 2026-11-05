"""Business migration 0002: identity guests and server-side sessions.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-05
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "identity_guests",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("nickname", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )
    op.create_table(
        "identity_sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "guest_id",
            sa.Text(),
            sa.ForeignKey("identity_guests.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.Text(), nullable=False),
    )
    op.create_index(
        "ix_identity_sessions_guest_id",
        "identity_sessions",
        ["guest_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_identity_sessions_guest_id", table_name="identity_sessions")
    op.drop_table("identity_sessions")
    op.drop_table("identity_guests")

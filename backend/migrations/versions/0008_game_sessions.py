"""Campaign session lifecycle, receipts and transactional stream facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "campaigns_game_sessions",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "campaign_id", sa.Text(), sa.ForeignKey("campaigns_campaigns.id"), nullable=False
        ),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("ended_at", sa.Text()),
        sa.CheckConstraint(
            "status IN ('running', 'paused', 'ended')", name="ck_game_session_status"
        ),
    )
    op.create_index(
        "uq_game_session_active",
        "campaigns_game_sessions",
        ["campaign_id"],
        unique=True,
        sqlite_where=sa.text("status IN ('running', 'paused')"),
    )
    op.create_table(
        "campaigns_session_state",
        sa.Column(
            "campaign_id", sa.Text(), sa.ForeignKey("campaigns_campaigns.id"), primary_key=True
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Text(), sa.ForeignKey("campaigns_game_sessions.id")),
        sa.CheckConstraint("revision >= 0", name="ck_session_revision"),
    )
    op.execute(
        "INSERT INTO campaigns_session_state (campaign_id, revision) "
        "SELECT id, 0 FROM campaigns_campaigns"
    )
    op.create_table(
        "campaigns_session_receipts",
        sa.Column(
            "campaign_id", sa.Text(), sa.ForeignKey("campaigns_campaigns.id"), primary_key=True
        ),
        sa.Column("actor_id", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
    )
    op.add_column("communication_events", sa.Column("game_session_revision", sa.Integer()))
    op.add_column("communication_events", sa.Column("game_session_state", sa.Text()))
    op.create_index(
        "uq_communication_game_session_revision",
        "communication_events",
        ["campaign_id", "game_session_revision"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_communication_game_session_revision", table_name="communication_events")
    op.drop_column("communication_events", "game_session_state")
    op.drop_column("communication_events", "game_session_revision")
    op.drop_table("campaigns_session_receipts")
    op.drop_table("campaigns_session_state")
    op.drop_table("campaigns_game_sessions")

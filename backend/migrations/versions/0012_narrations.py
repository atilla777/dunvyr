"""Durable narration requests, attempts and member retry receipts; no backfill."""

import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "communication_narrations",
        sa.Column("result_event_id", sa.Text(), primary_key=True),
        sa.Column("campaign_id", sa.Text(), nullable=False, index=True),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("attempt_token", sa.Text()),
        sa.Column("lease_until", sa.Float()),
        sa.Column("updated_at", sa.Float(), nullable=False),
        sa.Column("text", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.CheckConstraint("state IN ('pending','generating','ready','failed')"),
    )
    op.create_table(
        "communication_narration_starts",
        sa.Column("token", sa.Text(), primary_key=True),
        sa.Column("campaign_id", sa.Text(), nullable=False, index=True),
        sa.Column("started_at", sa.Float(), nullable=False),
    )
    op.create_table(
        "communication_narration_retries",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("actor_id", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("result_event_id", sa.Text(), nullable=False),
        sa.Column("expected_revision", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("communication_narration_retries")
    op.drop_table("communication_narration_starts")
    op.drop_table("communication_narrations")

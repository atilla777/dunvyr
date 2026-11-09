"""One durable campaign queue, exact command receipts and shared stream facts."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gameplay_queues",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("encounter_id", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.CheckConstraint("version >= 1", name="ck_queue_version"),
    )
    op.create_table(
        "gameplay_receipts",
        sa.Column("campaign_id", sa.Text(), primary_key=True),
        sa.Column("actor_id", sa.Text(), primary_key=True),
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=False),
    )
    op.add_column("communication_events", sa.Column("queue_version", sa.Integer()))
    op.add_column("communication_events", sa.Column("queue_state", sa.Text()))
    op.create_index(
        "uq_communication_queue_version",
        "communication_events",
        ["campaign_id", "queue_version"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_communication_queue_version", table_name="communication_events")
    op.drop_column("communication_events", "queue_state")
    op.drop_column("communication_events", "queue_version")
    op.drop_table("gameplay_receipts")
    op.drop_table("gameplay_queues")

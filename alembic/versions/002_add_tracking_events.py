"""add tracking_events table

Revision ID: 002
Revises: 001
Create Date: 2026-06-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "tracking_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_name", sa.String(), nullable=False),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("event_time", sa.Integer(), nullable=False),
        sa.Column("user_data", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("custom_data", postgresql.JSON(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("event_id", name="uq_tracking_events_event_id"),
    )
    op.create_index("ix_tracking_events_event_name", "tracking_events", ["event_name"])
    op.create_index("ix_tracking_events_event_id", "tracking_events", ["event_id"])


def downgrade() -> None:
    op.drop_index("ix_tracking_events_event_id", table_name="tracking_events")
    op.drop_index("ix_tracking_events_event_name", table_name="tracking_events")
    op.drop_table("tracking_events")

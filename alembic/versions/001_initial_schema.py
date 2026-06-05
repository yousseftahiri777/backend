"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("customer_name", sa.String(), nullable=False),
        sa.Column("phone", sa.String(), nullable=False),
        sa.Column("items", postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column("subtotal", sa.Float(), nullable=False),
        sa.Column("shipping", sa.Float(), nullable=False, server_default="0"),
        sa.Column("total", sa.Float(), nullable=False),
        sa.Column("upsell_accepted", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("upsell_product", sa.String(), nullable=True),
        sa.Column("ip_address", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(10), nullable=True),
        sa.Column("is_vpn", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("status", sa.String(), nullable=False, server_default="pending_confirmation"),
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="website"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", name="uq_orders_order_id"),
    )
    op.create_index("ix_orders_order_id", "orders", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_orders_order_id", table_name="orders")
    op.drop_table("orders")

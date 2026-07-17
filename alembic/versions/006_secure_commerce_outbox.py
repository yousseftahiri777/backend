"""compatibility marker after production rollback

Revision ID: 006
Revises: 005
Create Date: 2026-07-17 00:00:00.000000

The first 006 deployment may already have stamped production. Keep the revision
available so the stable application can start against either schema state.
"""

from typing import Sequence, Union


revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
"""secure commerce, public tokens, geo events, and Sheets outbox

Revision ID: 006
Revises: 005
Create Date: 2026-07-17 00:00:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM orders
            WHERE subtotal::text IN ('NaN', 'Infinity', '-Infinity')
               OR shipping::text IN ('NaN', 'Infinity', '-Infinity')
               OR total::text IN ('NaN', 'Infinity', '-Infinity')
               OR abs(subtotal) > 99999999.99
               OR abs(shipping) > 99999999.99
               OR abs(total) > 99999999.99
          ) OR EXISTS (
            SELECT 1 FROM order_items
            WHERE price::text IN ('NaN', 'Infinity', '-Infinity')
               OR abs(price) > 99999999.99
          ) THEN
            RAISE EXCEPTION 'Unsafe monetary values must be corrected before migration 006';
          END IF;
        END $$;
        """
    )
    # Numeric conversion preserves historical values; it does not recalculate totals.
    op.alter_column(
        "orders", "subtotal", type_=sa.Numeric(10, 2), postgresql_using="subtotal::numeric(10,2)"
    )
    op.alter_column(
        "orders", "shipping", type_=sa.Numeric(10, 2), postgresql_using="shipping::numeric(10,2)"
    )
    op.alter_column(
        "orders", "total", type_=sa.Numeric(10, 2), postgresql_using="total::numeric(10,2)"
    )
    op.alter_column(
        "order_items", "price", type_=sa.Numeric(10, 2), postgresql_using="price::numeric(10,2)"
    )
    op.add_column("orders", sa.Column("public_token_hash", sa.String(64), nullable=True))
    op.create_check_constraint(
        "ck_orders_public_token_hash_sha256",
        "orders",
        "public_token_hash IS NULL OR public_token_hash ~ '^[0-9a-f]{64}$'",
    )

    # Preserve the first historical occurrence and disambiguate duplicate event IDs.
    op.execute(
        """
        WITH ranked AS (
          SELECT id, event_id, row_number() OVER (
            PARTITION BY event_id ORDER BY created_at, id
          ) AS rn
          FROM orders
        )
        UPDATE orders AS o
        SET event_id = o.event_id || '-legacy-' || replace(o.id::text, '-', '')
        FROM ranked AS r
        WHERE o.id = r.id AND r.rn > 1
        """
    )
    op.create_unique_constraint("uq_orders_event_id", "orders", ["event_id"])

    op.add_column("tracking_events", sa.Column("country_code", sa.String(10), nullable=True))
    op.add_column(
        "tracking_events",
        sa.Column("is_vpn", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "tracking_events",
        sa.Column("is_valid", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_tracking_events_is_valid", "tracking_events", ["is_valid"])

    op.create_table(
        "sheet_sync_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "order_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("generation", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("order_id", name="uq_sheet_sync_jobs_order_id"),
        sa.CheckConstraint(
            "status IN ('pending','processing','synced','failed')",
            name="ck_sheet_sync_jobs_status",
        ),
        sa.CheckConstraint("generation >= 0", name="ck_sheet_sync_jobs_generation"),
        sa.CheckConstraint("attempts >= 0", name="ck_sheet_sync_jobs_attempts"),
    )
    op.create_index("ix_sheet_sync_jobs_order_id", "sheet_sync_jobs", ["order_id"])
    op.create_index("ix_sheet_sync_jobs_status", "sheet_sync_jobs", ["status"])
    op.create_index("ix_sheet_sync_jobs_next_attempt_at", "sheet_sync_jobs", ["next_attempt_at"])
    # Queue every historical order once so the first deployment reconciles an empty/stale Sheet.
    op.execute(
        """
        INSERT INTO sheet_sync_jobs
          (id, order_id, status, generation, attempts, next_attempt_at, created_at, updated_at)
        SELECT id, id, 'pending', 1, 0, now(), now(), now()
        FROM orders
        ON CONFLICT (order_id) DO NOTHING
        """
    )

    op.create_table(
        "admin_login_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ip_address", sa.String(64), nullable=False),
        sa.Column("username", sa.String(120), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_admin_login_attempts_ip_address", "admin_login_attempts", ["ip_address"])
    op.create_index("ix_admin_login_attempts_username", "admin_login_attempts", ["username"])
    op.create_index("ix_admin_login_attempts_created_at", "admin_login_attempts", ["created_at"])
    # Enforce new writes without mutating or rejecting anomalous historical rows.
    op.execute(
        "ALTER TABLE order_items ADD CONSTRAINT ck_order_items_qty "
        "CHECK (qty BETWEEN 1 AND 10) NOT VALID"
    )


def downgrade() -> None:
    op.drop_constraint("ck_order_items_qty", "order_items", type_="check")
    op.drop_table("admin_login_attempts")
    op.drop_table("sheet_sync_jobs")
    op.drop_index("ix_tracking_events_is_valid", table_name="tracking_events")
    op.drop_column("tracking_events", "is_valid")
    op.drop_column("tracking_events", "is_vpn")
    op.drop_column("tracking_events", "country_code")
    op.drop_constraint("uq_orders_event_id", "orders", type_="unique")
    op.drop_constraint("ck_orders_public_token_hash_sha256", "orders", type_="check")
    op.drop_column("orders", "public_token_hash")
    op.alter_column(
        "order_items", "price", type_=sa.Float(), postgresql_using="price::double precision"
    )
    for column in ("total", "shipping", "subtotal"):
        op.alter_column(
            "orders", column, type_=sa.Float(), postgresql_using=f"{column}::double precision"
        )

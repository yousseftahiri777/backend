import uuid
from datetime import datetime
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from app.database import Base


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(
            "public_token_hash IS NULL OR public_token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_orders_public_token_hash_sha256",
        ),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String, unique=True, nullable=False, index=True)
    customer_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    city = Column(String, nullable=True)
    items = Column(JSON, nullable=False)
    subtotal = Column(Numeric(10, 2), nullable=False)
    shipping = Column(Numeric(10, 2), nullable=False, default=0)
    total = Column(Numeric(10, 2), nullable=False)
    upsell_accepted = Column(Boolean, nullable=False, default=False)
    upsell_product = Column(String, nullable=True)
    ip_address = Column(String, nullable=False)
    country_code = Column(String(10), nullable=True)
    is_vpn = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="pending_confirmation")
    event_id = Column(String, nullable=False, unique=True)
    source = Column(String, nullable=False, default="website")
    public_token_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    order_items = relationship("OrderItem", back_populates="order", cascade="all, delete-orphan")
    sheet_sync_job = relationship(
        "SheetSyncJob", back_populates="order", cascade="all, delete-orphan", uselist=False
    )


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("qty BETWEEN 1 AND 10", name="ck_order_items_qty"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(UUID(as_uuid=True), ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(String, nullable=False)
    name_ar = Column(String, nullable=False)
    qty = Column(Integer, nullable=False)
    price = Column(Numeric(10, 2), nullable=False)

    order = relationship("Order", back_populates="order_items")


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_name = Column(String, nullable=False, index=True)
    event_id = Column(String, nullable=False, unique=True, index=True)
    event_time = Column(Integer, nullable=False)
    user_data = Column(JSON, nullable=False, default=dict)
    custom_data = Column(JSON, nullable=False, default=dict)
    ip_address = Column(String, nullable=True)
    country_code = Column(String(10), nullable=True)
    is_vpn = Column(Boolean, nullable=False, default=False)
    is_valid = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)


class PageView(Base):
    __tablename__ = "page_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(String, nullable=False, index=True)
    path = Column(String, nullable=False, index=True)
    referrer = Column(String, nullable=True)
    utm_source = Column(String, nullable=True)
    utm_medium = Column(String, nullable=True)
    utm_campaign = Column(String, nullable=True)
    ip_address = Column(String, nullable=False)
    country_code = Column(String(10), nullable=True)
    city = Column(String, nullable=True)
    is_vpn = Column(Boolean, nullable=False, default=False)
    is_valid = Column(Boolean, nullable=False, default=False, index=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)


class SheetSyncJob(Base):
    __tablename__ = "sheet_sync_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending','processing','synced','failed')",
            name="ck_sheet_sync_jobs_status",
        ),
        CheckConstraint("generation >= 0", name="ck_sheet_sync_jobs_generation"),
        CheckConstraint("attempts >= 0", name="ck_sheet_sync_jobs_attempts"),
    )

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    status = Column(String(20), nullable=False, default="pending", index=True)
    generation = Column(Integer, nullable=False, default=0)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    locked_at = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    order = relationship("Order", back_populates="sheet_sync_job")


class AdminLoginAttempt(Base):
    __tablename__ = "admin_login_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ip_address = Column(String(64), nullable=False, index=True)
    username = Column(String(120), nullable=False, index=True)
    succeeded = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

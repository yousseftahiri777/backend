import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Boolean, DateTime, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID
from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    order_id = Column(String, unique=True, nullable=False, index=True)
    customer_name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    items = Column(JSON, nullable=False)
    subtotal = Column(Float, nullable=False)
    shipping = Column(Float, nullable=False, default=0.0)
    total = Column(Float, nullable=False)
    upsell_accepted = Column(Boolean, nullable=False, default=False)
    upsell_product = Column(String, nullable=True)
    ip_address = Column(String, nullable=False)
    country_code = Column(String(10), nullable=True)
    is_vpn = Column(Boolean, nullable=False, default=False)
    status = Column(String, nullable=False, default="pending_confirmation")
    event_id = Column(String, nullable=False)
    source = Column(String, nullable=False, default="website")
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrackingEvent(Base):
    __tablename__ = "tracking_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_name = Column(String, nullable=False, index=True)
    event_id = Column(String, nullable=False, unique=True, index=True)
    event_time = Column(Integer, nullable=False)
    user_data = Column(JSON, nullable=False, default=dict)
    custom_data = Column(JSON, nullable=False, default=dict)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

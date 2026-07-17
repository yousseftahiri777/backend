import re
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, field_validator
import uuid

SAUDI_PHONE_RE = re.compile(r"^(\+9665|9665|05|5)\d{8}$")


class OrderItemSchema(BaseModel):
    productId: str
    nameAr: str
    qty: int
    price: float


class CreateOrderSchema(BaseModel):
    customerName: str
    phone: str
    city: Optional[str] = None
    items: List[OrderItemSchema]
    subtotal: float
    total: float
    shipping: float = 0.0
    upsellAccepted: bool = False
    upsellProduct: Optional[str] = None
    eventId: str
    source: str = "website"

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = v.strip().replace(" ", "").replace("-", "")
        if not SAUDI_PHONE_RE.match(cleaned):
            raise ValueError("رقم الجوال غير صحيح. يجب أن يكون رقماً سعودياً صحيحاً.")
        return cleaned

    @field_validator("customerName")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("الاسم قصير جداً.")
        return v

    @field_validator("items")
    @classmethod
    def validate_items(cls, v):
        if not v:
            raise ValueError("يجب أن يحتوي الطلب على منتج واحد على الأقل.")
        return v


class UpsellUpdateSchema(BaseModel):
    upsellAccepted: bool = True
    upsellProduct: str
    upsellPrice: float
    newTotal: float
    nameAr: Optional[str] = None


class ContactSchema(BaseModel):
    name: str
    email: str
    message: str


class OrderResponse(BaseModel):
    id: uuid.UUID
    orderId: str
    customerName: str
    phone: str
    city: Optional[str] = None
    items: List[Dict[str, Any]]
    subtotal: float
    shipping: float
    total: float
    upsellAccepted: bool
    upsellProduct: Optional[str]
    ipAddress: str
    countryCode: Optional[str]
    isVpn: bool
    status: str
    eventId: str
    source: str
    createdAt: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_order(cls, order):
        return cls(
            id=order.id,
            orderId=order.order_id,
            customerName=order.customer_name,
            phone=order.phone,
            city=getattr(order, "city", None),
            items=order.items,
            subtotal=order.subtotal,
            shipping=order.shipping,
            total=order.total,
            upsellAccepted=order.upsell_accepted,
            upsellProduct=order.upsell_product,
            ipAddress=order.ip_address,
            countryCode=order.country_code,
            isVpn=order.is_vpn,
            status=order.status,
            eventId=order.event_id,
            source=order.source,
            createdAt=order.created_at,
        )


class EventTrackSchema(BaseModel):
    event_name: str
    event_id: str
    event_time: int
    user_data: Dict[str, Any]
    custom_data: Dict[str, Any]


class PageViewSchema(BaseModel):
    sessionId: str
    path: str
    referrer: Optional[str] = None
    utmSource: Optional[str] = None
    utmMedium: Optional[str] = None
    utmCampaign: Optional[str] = None


class AdminLoginSchema(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    token: str
    expiresAt: int
    username: str


class AdminOrderListItem(BaseModel):
    id: uuid.UUID
    orderId: str
    customerName: str
    phone: str
    city: Optional[str] = None
    total: float
    status: str
    upsellAccepted: bool
    countryCode: Optional[str]
    isVpn: bool
    itemCount: int
    createdAt: datetime


class AdminOrderListResponse(BaseModel):
    orders: List[AdminOrderListItem]
    total: int
    page: int
    pageSize: int


class AdminOrderDetailResponse(OrderResponse):
    updatedAt: datetime
    orderItems: List[Dict[str, Any]]


class AdminStatusUpdateSchema(BaseModel):
    status: str

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        allowed = {
            "pending_confirmation",
            "confirmed",
            "preparing",
            "shipped",
            "delivered",
            "rto",
            "cancelled",
        }
        if v not in allowed:
            raise ValueError(f"Invalid status. Allowed: {', '.join(sorted(allowed))}")
        return v

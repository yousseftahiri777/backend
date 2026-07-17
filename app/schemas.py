import uuid
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

SAUDI_PHONE_RE = re.compile(r"^(\+9665|9665|05|5)\d{8}$")


class OrderItemSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    productId: str = Field(min_length=1, max_length=64)
    qty: int = Field(ge=1, le=10)


class CreateOrderSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customerName: str = Field(min_length=2, max_length=120)
    phone: str
    city: Optional[str] = Field(default=None, max_length=120)
    items: List[OrderItemSchema] = Field(min_length=1, max_length=3)
    eventId: str = Field(min_length=8, max_length=128)

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
        product_ids = [item.productId for item in v]
        if len(product_ids) != len(set(product_ids)):
            raise ValueError("لا يمكن تكرار المنتج في أكثر من سطر.")
        from app.product_catalog import PRODUCTS

        if any(product_id not in PRODUCTS for product_id in product_ids):
            raise ValueError("الطلب يحتوي على منتج غير صالح.")
        return v


class UpsellUpdateSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    upsellProduct: str = Field(min_length=1, max_length=64)


class ContactSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    email: str = Field(min_length=3, max_length=254)
    message: str = Field(min_length=1, max_length=4000)


class PublicOrderResponse(BaseModel):
    orderId: str
    orderToken: str
    customerName: str
    phone: str
    city: Optional[str] = None
    items: List[Dict[str, Any]]
    subtotal: float
    shipping: float
    total: float
    upsellAccepted: bool
    upsellProduct: Optional[str]
    status: str
    createdAt: datetime

    @classmethod
    def from_orm_order(cls, order, token: str):
        return cls(
            orderId=order.order_id,
            orderToken=token,
            customerName=order.customer_name,
            phone=order.phone,
            city=getattr(order, "city", None),
            items=order.items,
            subtotal=order.subtotal,
            shipping=order.shipping,
            total=order.total,
            upsellAccepted=order.upsell_accepted,
            upsellProduct=order.upsell_product,
            status=order.status,
            createdAt=order.created_at,
        )


class EventTrackSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_name: str = Field(min_length=1, max_length=64)
    event_id: str = Field(min_length=8, max_length=128)
    event_time: int = Field(gt=0)
    user_data: Dict[str, Any] = Field(default_factory=dict)
    custom_data: Dict[str, Any] = Field(default_factory=dict)


class PageViewSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessionId: str = Field(min_length=8, max_length=128)
    path: str = Field(min_length=1, max_length=512)
    referrer: Optional[str] = Field(default=None, max_length=512)
    utmSource: Optional[str] = Field(default=None, max_length=128)
    utmMedium: Optional[str] = Field(default=None, max_length=128)
    utmCampaign: Optional[str] = Field(default=None, max_length=128)


class AdminLoginSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=512)


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
    sheetSyncStatus: Optional[str] = None
    sheetSyncError: Optional[str] = None
    createdAt: datetime


class AdminOrderListResponse(BaseModel):
    orders: List[AdminOrderListItem]
    total: int
    page: int
    pageSize: int


class AdminOrderDetailResponse(BaseModel):
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
    updatedAt: datetime
    orderItems: List[Dict[str, Any]]
    sheetSyncStatus: Optional[str] = None
    sheetSyncError: Optional[str] = None


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

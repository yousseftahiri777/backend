import asyncio
import hashlib
import hmac
import logging
import secrets
import uuid
from decimal import Decimal
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, OrderItem
from app.schemas import CreateOrderSchema, PublicOrderResponse, UpsellUpdateSchema
from app.config import settings
from app.phone_utils import is_whitelisted_test_phone
from app.product_catalog import FREE_SHIPPING_THRESHOLD, SHIPPING_FEE, UPSELL_PRICE, get_product, price_items
from app.services.geo import get_client_ip, require_trusted_proxy, resolve_geo
from app.services.google_sheets import enqueue_sheet_sync
from app.services.pixels import send_fb_capi, send_tiktok_events, send_snap_capi

logger = logging.getLogger(__name__)
router = APIRouter()


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _public_token(order_id: str, event_id: str) -> str:
    secret = (
        settings.ORDER_TOKEN_SECRET.strip()
        or settings.ADMIN_JWT_SECRET.strip()
        or settings.ADMIN_ACCESS_KEY.strip()
        or settings.ADMIN_PASSWORD.strip()
        or settings.MAXMIND_LICENSE_KEY.strip()
    )
    if not secret:
        raise HTTPException(status_code=503, detail="Order security is not configured.")
    return hmac.new(
        secret.encode(),
        f"{order_id}:{event_id}".encode(),
        hashlib.sha256,
    ).hexdigest()


def _token_matches(order: Order, token: str | None) -> bool:
    return bool(
        token
        and order.public_token_hash
        and secrets.compare_digest(_token_hash(token), order.public_token_hash)
    )


def _require_order_token(order: Order, token: str | None) -> str:
    if not _token_matches(order, token):
        raise HTTPException(status_code=401, detail="رمز الطلب غير صالح.")
    return token or ""


def _same_order_request(order: Order, payload: CreateOrderSchema, trusted_items: list[dict]) -> bool:
    existing_items = [
        {"productId": item.get("productId"), "qty": item.get("qty")}
        for item in (order.items or [])
    ]
    requested_items = [
        {"productId": item["productId"], "qty": item["qty"]}
        for item in trusted_items
    ]
    return (
        order.customer_name == payload.customerName
        and order.phone == payload.phone
        and (order.city or None) == (payload.city or None)
        and existing_items == requested_items
    )


def _geo_block_detail(geo: dict) -> str:
    if geo.get("is_vpn"):
        return "تم رصد استخدام VPN. يرجى إيقاف VPN وإعادة المحاولة."
    if geo.get("is_proxy"):
        return "تم رصد استخدام بروكسي. يرجى إيقافه وإعادة المحاولة."
    if geo.get("is_suspicious"):
        return "تم رصد نشاط مشبوه من عنوان IP الخاص بك. يرجى المحاولة لاحقاً."
    return "عذراً، هذه الخدمة متاحة للمملكة العربية السعودية فقط."


@router.post("/orders", response_model=PublicOrderResponse, status_code=201)
async def create_order(
    payload: CreateOrderSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    require_trusted_proxy(request)
    trusted_items, subtotal, shipping, total = price_items(
        [item.model_dump() for item in payload.items]
    )
    existing = db.query(Order).filter(Order.event_id == payload.eventId).first()
    if existing:
        token = _public_token(existing.order_id, existing.event_id)
        if _same_order_request(existing, payload, trusted_items) and _token_matches(existing, token):
            return PublicOrderResponse.from_orm_order(existing, token)
        raise HTTPException(status_code=409, detail="معرّف الحدث مستخدم لطلب موجود.")

    ip = get_client_ip(request)
    recent_orders = (
        db.query(Order)
        .filter(
            Order.created_at >= datetime.utcnow() - timedelta(minutes=15),
            or_(Order.ip_address == ip, Order.phone == payload.phone),
        )
        .count()
    )
    if recent_orders >= 5:
        raise HTTPException(status_code=429, detail="طلبات كثيرة خلال وقت قصير. حاول لاحقاً.")
    test_locals = settings.get_test_phone_locals()
    is_test = is_whitelisted_test_phone(payload.phone, test_locals)

    if is_test:
        logger.info("Configured test phone bypass used")
        geo = {
            "country_code": "SA",
            "city": None,
            "is_vpn": False,
            "is_proxy": False,
            "is_suspicious": False,
            "is_allowed": True,
        }
    else:
        geo = await resolve_geo(request, ip)

    if not geo["is_allowed"]:
        logger.warning(
            "Order blocked: country=%s vpn=%s proxy=%s suspicious=%s",
            geo.get("country_code"), geo.get("is_vpn"),
            geo.get("is_proxy"), geo.get("is_suspicious"),
        )
        raise HTTPException(status_code=403, detail=_geo_block_detail(geo))

    order_id = f"lama-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"
    public_token = _public_token(order_id, payload.eventId)

    order = Order(
        order_id=order_id,
        customer_name=payload.customerName,
        phone=payload.phone,
        city=payload.city,
        items=trusted_items,
        subtotal=subtotal,
        shipping=shipping,
        total=total,
        upsell_accepted=False,
        upsell_product=None,
        ip_address=ip,
        country_code=geo.get("country_code"),
        is_vpn=geo.get("is_vpn", False),
        status="pending_confirmation",
        event_id=payload.eventId,
        source="website",
        public_token_hash=_token_hash(public_token),
    )

    try:
        db.add(order)
        db.flush()
        for item in trusted_items:
            db.add(
                OrderItem(
                    order_id=order.id,
                    product_id=item["productId"],
                    name_ar=item["nameAr"],
                    qty=item["qty"],
                    price=Decimal(str(item["price"])),
                )
            )
        enqueue_sheet_sync(db, order)
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.query(Order).filter(Order.event_id == payload.eventId).first()
        if existing:
            token = _public_token(existing.order_id, existing.event_id)
            if _same_order_request(existing, payload, trusted_items) and _token_matches(existing, token):
                return PublicOrderResponse.from_orm_order(existing, token)
        raise HTTPException(status_code=409, detail="معرّف الحدث مستخدم لطلب موجود.")
    db.refresh(order)

    event_data = {
        "event_name": "Purchase",
        "event_id": order.event_id,
        "event_time": int(order.created_at.timestamp()),
        "user_data": {
            "ph": order.phone,
            "client_ip_address": ip,
            "client_user_agent": request.headers.get("x-client-user-agent", "")[:512],
        },
        "custom_data": {
            "currency": "SAR",
            "value": float(order.total),
            "order_id": order.order_id,
            "contents": order.items,
        },
    }

    asyncio.create_task(send_fb_capi(event_data))
    asyncio.create_task(send_tiktok_events(event_data))
    asyncio.create_task(send_snap_capi(event_data))

    return PublicOrderResponse.from_orm_order(order, public_token)


@router.get("/orders/{order_id}", response_model=PublicOrderResponse)
async def get_order(
    order_id: str,
    order_token: str | None = Header(None, alias="X-Order-Token"),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود.")
    token = _require_order_token(order, order_token)
    return PublicOrderResponse.from_orm_order(order, token)


@router.patch("/orders/{order_id}/upsell", response_model=PublicOrderResponse)
async def update_order_upsell(
    order_id: str,
    payload: UpsellUpdateSchema,
    request: Request,
    order_token: str | None = Header(None, alias="X-Order-Token"),
    db: Session = Depends(get_db),
):
    require_trusted_proxy(request)
    order = (
        db.query(Order)
        .filter(Order.order_id == order_id)
        .with_for_update()
        .first()
    )
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود.")
    token = _require_order_token(order, order_token)

    if order.upsell_accepted:
        raise HTTPException(status_code=409, detail="تمت إضافة العرض الإضافي مسبقاً.")
    try:
        product = get_product(payload.upsellProduct)
    except ValueError:
        raise HTTPException(status_code=422, detail="المنتج الإضافي غير صالح.")
    if payload.upsellProduct in {item.get("productId") for item in (order.items or [])}:
        raise HTTPException(status_code=409, detail="المنتج موجود بالفعل في الطلب.")

    new_item = {
        "productId": payload.upsellProduct,
        "nameAr": str(product["nameAr"]),
        "sku": str(product["sku"]),
        "qty": 1,
        "price": float(UPSELL_PRICE),
    }
    updated_items = list(order.items or [])
    updated_items.append(new_item)

    order.upsell_accepted = True
    order.upsell_product = payload.upsellProduct
    order.items = updated_items
    order.subtotal = Decimal(order.subtotal) + UPSELL_PRICE
    order.shipping = (
        Decimal("0.00")
        if Decimal(order.subtotal) >= FREE_SHIPPING_THRESHOLD
        else SHIPPING_FEE
    )
    order.total = Decimal(order.subtotal) + Decimal(order.shipping)
    order.updated_at = datetime.utcnow()

    db.add(OrderItem(
        order_id=order.id,
        product_id=payload.upsellProduct,
        name_ar=str(product["nameAr"]),
        qty=1,
        price=UPSELL_PRICE,
    ))
    enqueue_sheet_sync(db, order)
    db.commit()
    db.refresh(order)
    return PublicOrderResponse.from_orm_order(order, token)

import uuid
import logging
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Order, OrderItem
from app.schemas import CreateOrderSchema, OrderResponse
from app.config import settings
from app.services import maxmind
from app.services.google_sheets import send_to_sheets
from app.services.pixels import send_fb_capi, send_tiktok_events, send_snap_capi

logger = logging.getLogger(__name__)
router = APIRouter()

# Whitelisted test phones bypass all geo/VPN checks (see TEST_PHONE in .env)
_TEST_PHONES: set[str] = {
    settings.TEST_PHONE.strip(),
    "0513194328",
}


def get_client_ip(request: Request) -> str:
    # Cloudflare sets this header with the real visitor IP
    cf_ip = request.headers.get("CF-Connecting-IP")
    if cf_ip:
        return cf_ip.strip()
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "127.0.0.1"


def _geo_block_detail(geo: dict) -> str:
    if geo.get("is_vpn"):
        return "تم رصد استخدام VPN. يرجى إيقاف VPN وإعادة المحاولة."
    if geo.get("is_proxy"):
        return "تم رصد استخدام بروكسي. يرجى إيقافه وإعادة المحاولة."
    if geo.get("is_suspicious"):
        return "تم رصد نشاط مشبوه من عنوان IP الخاص بك. يرجى المحاولة لاحقاً."
    return "عذراً، هذه الخدمة متاحة للمملكة العربية السعودية فقط."


@router.post("/orders", response_model=OrderResponse, status_code=201)
async def create_order(
    payload: CreateOrderSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    ip = get_client_ip(request)
    is_test = payload.phone in _TEST_PHONES

    if is_test:
        logger.info("Test phone %s — bypassing geo checks for IP %s", payload.phone, ip)
        geo = {
            "country_code": "SA",
            "city": None,
            "is_vpn": False,
            "is_proxy": False,
            "is_suspicious": False,
            "is_allowed": True,
        }
    else:
        # Use Cloudflare country header first (free, reliable, no API calls)
        cf_country = request.headers.get("CF-IPCountry", "").upper().strip()
        if cf_country and cf_country not in ("", "XX", "T1"):
            is_allowed = cf_country == "SA"
            geo = {
                "country_code": cf_country,
                "city": None,
                "is_vpn": cf_country == "T1",
                "is_proxy": False,
                "is_suspicious": not is_allowed,
                "is_allowed": is_allowed,
            }
            logger.info("Cloudflare country check: IP=%s country=%s allowed=%s", ip, cf_country, is_allowed)
        else:
            # Fallback to MaxMind if Cloudflare header not available
            geo = await maxmind.check_ip(ip)

    if not geo["is_allowed"]:
        logger.warning(
            "Order blocked: IP=%s country=%s vpn=%s proxy=%s suspicious=%s",
            ip, geo.get("country_code"), geo.get("is_vpn"),
            geo.get("is_proxy"), geo.get("is_suspicious"),
        )
        raise HTTPException(status_code=403, detail=_geo_block_detail(geo))

    order_id = f"LM-{datetime.utcnow().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

    order = Order(
        order_id=order_id,
        customer_name=payload.customerName,
        phone=payload.phone,
        items=[item.model_dump() for item in payload.items],
        subtotal=payload.subtotal,
        shipping=payload.shipping,
        total=payload.total,
        upsell_accepted=payload.upsellAccepted,
        upsell_product=payload.upsellProduct,
        ip_address=ip,
        country_code=geo.get("country_code"),
        is_vpn=geo.get("is_vpn", False),
        status="pending_confirmation",
        event_id=payload.eventId,
        source=payload.source,
    )

    db.add(order)
    db.flush()

    for item in payload.items:
        db.add(OrderItem(
            order_id=order.id,
            product_id=item.productId,
            name_ar=item.nameAr,
            qty=item.qty,
            price=item.price,
        ))

    db.commit()
    db.refresh(order)

    order_dict = {
        "orderId": order.order_id,
        "customerName": order.customer_name,
        "phone": order.phone,
        "items": order.items,
        "subtotal": order.subtotal,
        "shipping": order.shipping,
        "total": order.total,
        "upsellAccepted": order.upsell_accepted,
        "upsellProduct": order.upsell_product,
        "ipAddress": order.ip_address,
        "status": order.status,
        "createdAt": order.created_at.isoformat(),
    }

    event_data = {
        "event_name": "Purchase",
        "event_id": order.event_id,
        "event_time": int(order.created_at.timestamp()),
        "user_data": {
            "ph": order.phone,
            "client_ip_address": ip,
        },
        "custom_data": {
            "currency": "SAR",
            "value": order.total,
            "order_id": order.order_id,
            "contents": order.items,
        },
    }

    asyncio.create_task(send_to_sheets(order_dict))
    asyncio.create_task(send_fb_capi(event_data))
    asyncio.create_task(send_tiktok_events(event_data))
    asyncio.create_task(send_snap_capi(event_data))

    return OrderResponse.from_orm_order(order)


@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="الطلب غير موجود.")
    return OrderResponse.from_orm_order(order)

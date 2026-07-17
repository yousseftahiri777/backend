import csv
import io
import logging
from datetime import datetime, date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.config import settings
from app.database import get_db
from app.models import Order, OrderItem
from app.schemas import (
    AdminLoginSchema,
    AdminLoginResponse,
    AdminOrderDetailResponse,
    AdminOrderListItem,
    AdminOrderListResponse,
    AdminStatusUpdateSchema,
    OrderResponse,
)
from app.services.admin_analytics import get_metrics
from app.services.admin_auth import create_admin_token, require_admin, verify_admin_credentials

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ORDER_FILTER = (
    (Order.country_code == "SA")
    & (Order.is_vpn.is_(False))
)


def _csv_safe(value: object) -> object:
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@")):
        return f"'{value}"
    return value


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(payload: AdminLoginSchema):
    if not settings.ADMIN_USERNAME.strip() or not settings.ADMIN_PASSWORD.strip():
        raise HTTPException(
            status_code=503,
            detail="Admin login is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD.",
        )
    if not verify_admin_credentials(payload.username.strip(), payload.password):
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token, expires_at = create_admin_token(payload.username.strip())
    return AdminLoginResponse(token=token, expiresAt=expires_at, username=payload.username.strip())


@router.get("/metrics")
async def admin_metrics(
    start: Optional[date] = Query(None, description="Start date (YYYY-MM-DD)"),
    end: Optional[date] = Query(None, description="End date (YYYY-MM-DD)"),
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    today = date.today()
    end_date = end or today
    start_date = start or (today.replace(day=1) if today.day > 1 else today)
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start must be before or equal to end")

    return get_metrics(
        db,
        datetime.combine(start_date, datetime.min.time()),
        datetime.combine(end_date, datetime.min.time()),
    )


@router.get("/orders", response_model=AdminOrderListResponse)
async def admin_list_orders(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(Order).filter(VALID_ORDER_FILTER)

    if status:
        q = q.filter(Order.status == status)
    if start:
        q = q.filter(Order.created_at >= datetime.combine(start, datetime.min.time()))
    if end:
        q = q.filter(Order.created_at < datetime.combine(end, datetime.max.time()))
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Order.order_id.ilike(term),
                Order.customer_name.ilike(term),
                Order.phone.ilike(term),
                Order.city.ilike(term),
            )
        )

    total = q.count()
    orders = (
        q.order_by(Order.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items: list[AdminOrderListItem] = []
    for order in orders:
        item_count = len(order.items or [])
        items.append(
            AdminOrderListItem(
                id=order.id,
                orderId=order.order_id,
                customerName=order.customer_name,
                phone=order.phone,
                city=order.city,
                total=order.total,
                status=order.status,
                upsellAccepted=order.upsell_accepted,
                countryCode=order.country_code,
                isVpn=order.is_vpn,
                itemCount=item_count,
                createdAt=order.created_at,
            )
        )

    return AdminOrderListResponse(orders=items, total=total, page=page, pageSize=page_size)


@router.get("/orders/export")
async def admin_export_orders(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    q = db.query(Order).filter(VALID_ORDER_FILTER)
    if status:
        q = q.filter(Order.status == status)
    if start:
        q = q.filter(Order.created_at >= datetime.combine(start, datetime.min.time()))
    if end:
        q = q.filter(Order.created_at < datetime.combine(end, datetime.max.time()))
    if search:
        term = f"%{search.strip()}%"
        q = q.filter(
            or_(
                Order.order_id.ilike(term),
                Order.customer_name.ilike(term),
                Order.phone.ilike(term),
                Order.city.ilike(term),
            )
        )

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(
        [
            "DATE",
            "ORDER ID",
            "COUNTRY",
            "NAME",
            "PHONE",
            "CITY",
            "PRODUCT",
            "QUANTITY",
            "TOTAL PRICE",
            "CURRENCY",
            "STATUS",
        ]
    )
    for order in q.order_by(Order.created_at.desc()).all():
        order_items = order.items or []
        products = " / ".join(
            str(item.get("nameAr") or item.get("productId") or "") for item in order_items
        )
        quantities = " / ".join(str(item.get("qty", 1)) for item in order_items)
        writer.writerow(
            [
                order.created_at.strftime("%d/%m/%Y %H:%M"),
                order.order_id,
                order.country_code or "SA",
                _csv_safe(order.customer_name),
                _csv_safe(order.phone),
                _csv_safe(order.city or ""),
                _csv_safe(products),
                quantities,
                order.total,
                "SAR",
                order.status,
            ]
        )

    filename = f"lama-orders-{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/orders/{order_id}", response_model=AdminOrderDetailResponse)
async def admin_get_order(
    order_id: str,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_items = (
        db.query(OrderItem)
        .filter(OrderItem.order_id == order.id)
        .all()
    )
    base = OrderResponse.from_orm_order(order)
    return AdminOrderDetailResponse(
        **base.model_dump(),
        updatedAt=order.updated_at,
        orderItems=[
            {
                "productId": i.product_id,
                "nameAr": i.name_ar,
                "qty": i.qty,
                "price": i.price,
                "lineTotal": round(i.qty * i.price, 2),
            }
            for i in order_items
        ],
    )


@router.patch("/orders/{order_id}/status", response_model=OrderResponse)
async def admin_update_order_status(
    order_id: str,
    payload: AdminStatusUpdateSchema,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status
    order.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(order)
    logger.info("Order %s status updated to %s by admin", order_id, payload.status)
    return OrderResponse.from_orm_order(order)

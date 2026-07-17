import logging
from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import or_, text

from app.config import settings
from app.database import get_db
from app.models import AdminLoginAttempt, Order, OrderItem
from app.schemas import (
    AdminLoginSchema,
    AdminLoginResponse,
    AdminOrderDetailResponse,
    AdminOrderListItem,
    AdminOrderListResponse,
    AdminStatusUpdateSchema,
)
from app.services.admin_analytics import get_metrics
from app.services.admin_auth import create_admin_token, require_admin, verify_admin_credentials
from app.services.geo import get_client_ip, is_trusted_proxy
from app.services.google_sheets import enqueue_sheet_sync

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"])

VALID_ORDER_FILTER = (
    (Order.country_code == "SA")
    & (Order.is_vpn.is_(False))
)
KSA_UTC_OFFSET = timedelta(hours=3)


def _ksa_day_start_utc(value: date) -> datetime:
    return datetime.combine(value, datetime.min.time()) - KSA_UTC_OFFSET


def _order_detail(order: Order, db: Session) -> AdminOrderDetailResponse:
    order_items = db.query(OrderItem).filter(OrderItem.order_id == order.id).all()
    return AdminOrderDetailResponse(
        id=order.id,
        orderId=order.order_id,
        customerName=order.customer_name,
        phone=order.phone,
        city=order.city,
        items=order.items,
        subtotal=float(order.subtotal),
        shipping=float(order.shipping),
        total=float(order.total),
        upsellAccepted=order.upsell_accepted,
        upsellProduct=order.upsell_product,
        ipAddress=order.ip_address,
        countryCode=order.country_code,
        isVpn=order.is_vpn,
        status=order.status,
        eventId=order.event_id,
        source=order.source,
        createdAt=order.created_at,
        updatedAt=order.updated_at,
        sheetSyncStatus=order.sheet_sync_job.status if order.sheet_sync_job else None,
        sheetSyncError=order.sheet_sync_job.last_error if order.sheet_sync_job else None,
        orderItems=[
            {
                "productId": item.product_id,
                "nameAr": item.name_ar,
                "qty": item.qty,
                "price": float(item.price),
                "lineTotal": round(item.qty * float(item.price), 2),
            }
            for item in order_items
        ],
    )


@router.post("/login", response_model=AdminLoginResponse)
async def admin_login(
    payload: AdminLoginSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    if settings.BACKEND_PROXY_SECRET.strip() and not is_trusted_proxy(request):
        raise HTTPException(status_code=403, detail="Admin login must use the trusted frontend.")
    if (
        not settings.ADMIN_USERNAME.strip()
        or not settings.ADMIN_PASSWORD.strip()
    ):
        raise HTTPException(
            status_code=503,
            detail="Admin login is not configured. Set ADMIN_USERNAME and ADMIN_PASSWORD.",
        )
    username = payload.username.strip()
    ip = get_client_ip(request)
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"admin-login:{ip}:{username.lower()}"},
    )
    db.query(AdminLoginAttempt).filter(
        AdminLoginAttempt.created_at < datetime.utcnow() - timedelta(days=1)
    ).delete(synchronize_session=False)
    cutoff = datetime.utcnow() - timedelta(minutes=15)
    failures = (
        db.query(AdminLoginAttempt)
        .filter(
            AdminLoginAttempt.succeeded.is_(False),
            AdminLoginAttempt.created_at >= cutoff,
            or_(
                AdminLoginAttempt.ip_address == ip,
                AdminLoginAttempt.username == username,
            ),
        )
        .count()
    )
    if failures >= 5:
        raise HTTPException(status_code=429, detail="Too many login attempts. Try again later.")
    valid = verify_admin_credentials(username, payload.password)
    db.add(
        AdminLoginAttempt(
            ip_address=ip,
            username=username,
            succeeded=valid,
        )
    )
    db.commit()
    if not valid:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    token, expires_at = create_admin_token(username)
    return AdminLoginResponse(token=token, expiresAt=expires_at, username=username)


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

    result = get_metrics(
        db,
        _ksa_day_start_utc(start_date),
        _ksa_day_start_utc(end_date),
    )
    result["period"] = {"start": start_date.isoformat(), "end": end_date.isoformat()}
    return result


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
        q = q.filter(Order.created_at >= _ksa_day_start_utc(start))
    if end:
        q = q.filter(Order.created_at < _ksa_day_start_utc(end + timedelta(days=1)))
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
                sheetSyncStatus=order.sheet_sync_job.status if order.sheet_sync_job else None,
                sheetSyncError=order.sheet_sync_job.last_error if order.sheet_sync_job else None,
                createdAt=order.created_at,
            )
        )

    return AdminOrderListResponse(orders=items, total=total, page=page, pageSize=page_size)


@router.get("/orders/{order_id}", response_model=AdminOrderDetailResponse)
async def admin_get_order(
    order_id: str,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return _order_detail(order, db)


@router.patch("/orders/{order_id}/status", response_model=AdminOrderDetailResponse)
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
    enqueue_sheet_sync(db, order)
    db.commit()
    db.refresh(order)
    logger.info("Order %s status updated to %s by admin", order_id, payload.status)
    return _order_detail(order, db)


@router.post("/orders/{order_id}/sheet-sync")
async def admin_retry_sheet_sync(
    order_id: str,
    _admin: str = Depends(require_admin),
    db: Session = Depends(get_db),
):
    order = db.query(Order).filter(Order.order_id == order_id).first()
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    job = enqueue_sheet_sync(db, order)
    db.commit()
    db.refresh(job)
    return {"orderId": order.order_id, "sheetSyncStatus": job.status}

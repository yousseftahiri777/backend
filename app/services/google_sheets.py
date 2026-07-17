import logging
import asyncio
from datetime import datetime, timedelta

import httpx
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Order, SheetSyncJob
from app.phone_utils import format_ksa_phone_international
from app.product_catalog import get_product_sku

logger = logging.getLogger(__name__)


def _parse_created_at(order_data: dict) -> datetime:
    raw = order_data.get("createdAt")
    if isinstance(raw, datetime):
        return raw
    if isinstance(raw, str) and raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            pass
    return datetime.utcnow()


def build_sheets_payload(order_data: dict) -> dict:
    """Build payload matching Orders sheet columns."""
    items = order_data.get("items") or []
    created_at = _parse_created_at(order_data) + timedelta(hours=3)

    product_names = "/".join(str(item.get("nameAr") or item.get("productId") or "") for item in items)
    skus = "/".join(get_product_sku(str(item.get("productId", ""))) for item in items)
    quantities = "/".join(str(item.get("qty", 1)) for item in items)

    return {
        "secret": settings.GOOGLE_SHEETS_WEBHOOK_SECRET,
        "date": created_at.strftime("%d/%m/%Y"),
        "orderId": order_data.get("orderId", ""),
        "country": "KSA",
        "name": order_data.get("customerName", ""),
        "phone": format_ksa_phone_international(order_data.get("phone", "")),
        "product": product_names,
        "sku": skus,
        "quantity": quantities,
        "subtotal": order_data.get("subtotal", 0),
        "shipping": order_data.get("shipping", 0),
        "totalPrice": order_data.get("total", 0),
        "currency": "SAR",
        "status": order_data.get("status", ""),
        "city": order_data.get("city", ""),
        "source": order_data.get("source", "website"),
        "upsell": order_data.get("upsellProduct") or "",
    }


async def send_to_sheets(order_data: dict) -> None:
    if not settings.GOOGLE_SHEETS_WEBHOOK_URL:
        raise RuntimeError("GOOGLE_SHEETS_WEBHOOK_URL is not configured")

    payload = build_sheets_payload(order_data)

    async with httpx.AsyncClient(timeout=10.0, follow_redirects=True) as client:
        response = await client.post(settings.GOOGLE_SHEETS_WEBHOOK_URL, json=payload)
        response.raise_for_status()
        try:
            body = response.json()
        except ValueError as exc:
            raise RuntimeError("Sheets webhook returned non-JSON response") from exc
        if body.get("success") is not True:
            raise RuntimeError(f"Sheets webhook rejected payload: {body.get('error', 'unknown error')}")
    logger.info("Google Sheets webhook sent for order %s", payload["orderId"])


def order_to_dict(order: Order) -> dict:
    return {
        "orderId": order.order_id,
        "customerName": order.customer_name,
        "phone": order.phone,
        "city": order.city,
        "items": order.items,
        "subtotal": float(order.subtotal),
        "shipping": float(order.shipping),
        "total": float(order.total),
        "status": order.status,
        "source": order.source,
        "upsellProduct": order.upsell_product,
        "createdAt": order.created_at,
    }


def enqueue_sheet_sync(db: Session, order: Order) -> SheetSyncJob:
    """Upsert one latest-state job per order inside the caller's transaction."""
    db.flush()
    db.execute(
        pg_insert(SheetSyncJob)
        .values(order_id=order.id)
        .on_conflict_do_nothing(index_elements=[SheetSyncJob.order_id])
    )
    job = (
        db.query(SheetSyncJob)
        .filter(SheetSyncJob.order_id == order.id)
        .with_for_update()
        .first()
    )
    if job is None:
        raise RuntimeError("Could not create Sheets synchronization job")
    job.generation = (job.generation or 0) + 1
    job.status = "pending"
    job.next_attempt_at = datetime.utcnow()
    job.locked_at = None
    job.last_error = None
    job.updated_at = datetime.utcnow()
    return job


def _claim_job(db: Session) -> tuple[SheetSyncJob, int] | None:
    now = datetime.utcnow()
    stale = now - timedelta(minutes=10)
    job = (
        db.query(SheetSyncJob)
        .filter(
            SheetSyncJob.next_attempt_at <= now,
            (
                (SheetSyncJob.status.in_(("pending", "failed")))
                | ((SheetSyncJob.status == "processing") & (SheetSyncJob.locked_at < stale))
            ),
        )
        .order_by(SheetSyncJob.next_attempt_at, SheetSyncJob.created_at)
        .with_for_update(skip_locked=True)
        .first()
    )
    if job:
        claimed_generation = job.generation
        job.status = "processing"
        job.locked_at = now
        job.attempts += 1
        job.updated_at = now
        db.commit()
        db.refresh(job)
        return job, claimed_generation
    return None


async def process_one_sheet_job() -> bool:
    db = SessionLocal()
    try:
        claimed = _claim_job(db)
        if not claimed:
            return False
        job, claimed_generation = claimed
        order = db.query(Order).filter(Order.id == job.order_id).first()
        if not order:
            job.status = "failed"
            job.last_error = "Order no longer exists"
            db.commit()
            return True
        try:
            await send_to_sheets(order_to_dict(order))
        except asyncio.CancelledError:
            db.refresh(job)
            if job.generation == claimed_generation:
                job.status = "pending"
                job.locked_at = None
                job.next_attempt_at = datetime.utcnow()
                db.commit()
            raise
        except Exception as exc:
            logger.error("Sheets sync failed for %s: %s", order.order_id, exc)
            db.refresh(job)
            if job.generation != claimed_generation:
                job.status = "pending"
                job.locked_at = None
                db.commit()
                return True
            job.status = "failed"
            job.last_error = str(exc)[:2000]
            delay = min(3600, 2 ** min(job.attempts, 10) * 5)
            job.next_attempt_at = datetime.utcnow() + timedelta(seconds=delay)
        else:
            db.refresh(job)
            if job.generation != claimed_generation:
                job.status = "pending"
                job.locked_at = None
                db.commit()
                return True
            job.status = "synced"
            job.last_error = None
            job.next_attempt_at = datetime.utcnow()
        job.locked_at = None
        job.updated_at = datetime.utcnow()
        db.commit()
        return True
    finally:
        db.close()


async def sheet_sync_loop() -> None:
    while True:
        try:
            worked = await process_one_sheet_job()
            await asyncio.sleep(0.25 if worked else settings.SHEET_SYNC_POLL_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected Sheets outbox worker error")
            await asyncio.sleep(settings.SHEET_SYNC_POLL_SECONDS)

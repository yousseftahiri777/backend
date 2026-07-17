"""Admin dashboard metrics — counts only valid KSA, non-VPN traffic."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, PageView, TrackingEvent

VALID_ORDER_FILTER = (
    (Order.country_code == "SA")
    & (Order.is_vpn.is_(False))
)

VALID_PAGE_VIEW_FILTER = PageView.is_valid.is_(True)
CONFIRMED_STATUSES = ("confirmed", "preparing", "shipped", "delivered")


def get_metrics(db: Session, start: datetime, end: datetime) -> dict[str, Any]:
    end_exclusive = end + timedelta(days=1)

    clicks = (
        db.query(func.count(PageView.id))
        .filter(
            VALID_PAGE_VIEW_FILTER,
            PageView.created_at >= start,
            PageView.created_at < end_exclusive,
        )
        .scalar()
        or 0
    )

    unique_visitors = (
        db.query(func.count(func.distinct(PageView.session_id)))
        .filter(
            VALID_PAGE_VIEW_FILTER,
            PageView.created_at >= start,
            PageView.created_at < end_exclusive,
        )
        .scalar()
        or 0
    )

    orders_q = db.query(Order).filter(
        VALID_ORDER_FILTER,
        Order.created_at >= start,
        Order.created_at < end_exclusive,
    )
    order_count = orders_q.count()
    confirmed_order_count = orders_q.filter(Order.status.in_(CONFIRMED_STATUSES)).count()
    revenue = (
        db.query(func.coalesce(func.sum(Order.total), 0.0))
        .filter(
            VALID_ORDER_FILTER,
            Order.created_at >= start,
            Order.created_at < end_exclusive,
        )
        .scalar()
        or 0.0
    )

    upsell_count = (
        db.query(func.count(Order.id))
        .filter(
            VALID_ORDER_FILTER,
            Order.upsell_accepted.is_(True),
            Order.created_at >= start,
            Order.created_at < end_exclusive,
        )
        .scalar()
        or 0
    )

    checkout_starts = (
        db.query(func.count(TrackingEvent.id))
        .filter(
            TrackingEvent.event_name == "InitiateCheckout",
            TrackingEvent.created_at >= start,
            TrackingEvent.created_at < end_exclusive,
        )
        .scalar()
        or 0
    )

    blocked_clicks = (
        db.query(func.count(PageView.id))
        .filter(
            PageView.is_valid.is_(False),
            PageView.created_at >= start,
            PageView.created_at < end_exclusive,
        )
        .scalar()
        or 0
    )

    conversion_rate = round((order_count / unique_visitors * 100), 2) if unique_visitors else 0.0
    checkout_rate = round((checkout_starts / unique_visitors * 100), 2) if unique_visitors else 0.0
    checkout_conversion_rate = round((order_count / checkout_starts * 100), 2) if checkout_starts else 0.0
    aov = round(revenue / order_count, 2) if order_count else 0.0
    upsell_rate = round((upsell_count / order_count * 100), 2) if order_count else 0.0

    daily_rows = (
        db.query(
            cast(Order.created_at, Date).label("day"),
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total), 0.0).label("revenue"),
        )
        .filter(
            VALID_ORDER_FILTER,
            Order.created_at >= start,
            Order.created_at < end_exclusive,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    click_rows = (
        db.query(
            cast(PageView.created_at, Date).label("day"),
            func.count(PageView.id).label("clicks"),
            func.count(func.distinct(PageView.session_id)).label("visitors"),
        )
        .filter(
            VALID_PAGE_VIEW_FILTER,
            PageView.created_at >= start,
            PageView.created_at < end_exclusive,
        )
        .group_by("day")
        .order_by("day")
        .all()
    )

    daily_map: dict[str, dict] = {}
    for row in daily_rows:
        key = row.day.isoformat()
        daily_map[key] = {"date": key, "orders": row.orders, "revenue": float(row.revenue), "clicks": 0, "visitors": 0}
    for row in click_rows:
        key = row.day.isoformat()
        if key not in daily_map:
            daily_map[key] = {"date": key, "orders": 0, "revenue": 0.0, "clicks": 0, "visitors": 0}
        daily_map[key]["clicks"] = row.clicks
        daily_map[key]["visitors"] = row.visitors

    daily = sorted(daily_map.values(), key=lambda x: x["date"])

    product_rows = (
        db.query(
            OrderItem.product_id,
            OrderItem.name_ar,
            func.sum(OrderItem.qty).label("units"),
            func.coalesce(func.sum(OrderItem.qty * OrderItem.price), 0.0).label("revenue"),
        )
        .join(Order, Order.id == OrderItem.order_id)
        .filter(
            VALID_ORDER_FILTER,
            Order.created_at >= start,
            Order.created_at < end_exclusive,
        )
        .group_by(OrderItem.product_id, OrderItem.name_ar)
        .order_by(func.sum(OrderItem.qty).desc())
        .all()
    )

    status_rows = (
        db.query(Order.status, func.count(Order.id))
        .filter(
            VALID_ORDER_FILTER,
            Order.created_at >= start,
            Order.created_at < end_exclusive,
        )
        .group_by(Order.status)
        .all()
    )

    top_pages = (
        db.query(PageView.path, func.count(PageView.id).label("views"))
        .filter(
            VALID_PAGE_VIEW_FILTER,
            PageView.created_at >= start,
            PageView.created_at < end_exclusive,
        )
        .group_by(PageView.path)
        .order_by(func.count(PageView.id).desc())
        .limit(10)
        .all()
    )

    city_rows = (
        db.query(Order.city, func.count(Order.id))
        .filter(
            VALID_ORDER_FILTER,
            Order.created_at >= start,
            Order.created_at < end_exclusive,
            Order.city.isnot(None),
            Order.city != "",
        )
        .group_by(Order.city)
        .order_by(func.count(Order.id).desc())
        .limit(10)
        .all()
    )

    channel_rows = (
        db.query(
            Order.source,
            func.count(Order.id).label("orders"),
            func.coalesce(func.sum(Order.total), 0.0).label("revenue"),
        )
        .filter(
            VALID_ORDER_FILTER,
            Order.created_at >= start,
            Order.created_at < end_exclusive,
        )
        .group_by(Order.source)
        .order_by(func.sum(Order.total).desc())
        .all()
    )

    return {
        "period": {"start": start.date().isoformat(), "end": end.date().isoformat()},
        "summary": {
            "clicks": clicks,
            "uniqueVisitors": unique_visitors,
            "orders": order_count,
            "confirmedOrders": confirmed_order_count,
            "revenue": round(float(revenue), 2),
            "aov": aov,
            "conversionRate": conversion_rate,
            "checkoutStarts": checkout_starts,
            "checkoutRate": checkout_rate,
            "checkoutConversionRate": checkout_conversion_rate,
            "upsellAccepted": upsell_count,
            "upsellRate": upsell_rate,
            "blockedClicks": blocked_clicks,
        },
        "daily": daily,
        "products": [
            {
                "productId": r.product_id,
                "nameAr": r.name_ar,
                "units": int(r.units or 0),
                "revenue": round(float(r.revenue or 0), 2),
            }
            for r in product_rows
        ],
        "statusBreakdown": {status: count for status, count in status_rows},
        "topPages": [{"path": path, "views": views} for path, views in top_pages],
        "topCities": [{"city": city, "orders": count} for city, count in city_rows],
        "channels": [
            {
                "source": source or "unknown",
                "orders": int(orders or 0),
                "revenue": round(float(channel_revenue or 0), 2),
            }
            for source, orders, channel_revenue in channel_rows
        ],
    }

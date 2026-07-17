import asyncio
import json
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TrackingEvent
from app.schemas import EventTrackSchema
from app.services.geo import get_client_ip, require_trusted_proxy, resolve_geo
from app.services.pixels import send_fb_capi, send_tiktok_events, send_snap_capi

router = APIRouter()


@router.post("/events/track", status_code=202)
async def track_event(
    payload: EventTrackSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    require_trusted_proxy(request)
    event_data = payload.model_dump()
    if len(json.dumps(event_data, ensure_ascii=False).encode("utf-8")) > 32_768:
        raise HTTPException(status_code=413, detail="Event payload too large")
    ip = get_client_ip(request)
    recent_count = (
        db.query(TrackingEvent)
        .filter(
            TrackingEvent.ip_address == ip,
            TrackingEvent.created_at >= datetime.utcnow() - timedelta(minutes=1),
        )
        .count()
    )
    if recent_count >= 120:
        raise HTTPException(status_code=429, detail="Too many events")
    geo = await resolve_geo(request, ip)
    event_data["user_data"] = {
        **payload.user_data,
        "client_ip_address": ip,
        "client_user_agent": request.headers.get("x-client-user-agent", "")[:512],
    }

    # Save to DB
    event = TrackingEvent(
        id=uuid.uuid4(),
        event_name=payload.event_name,
        event_id=payload.event_id,
        event_time=payload.event_time,
        user_data=payload.user_data,
        custom_data=payload.custom_data,
        ip_address=ip,
        country_code=geo.get("country_code"),
        is_vpn=bool(geo.get("is_vpn")),
        is_valid=bool(geo.get("is_allowed")),
        created_at=datetime.utcnow(),
    )
    try:
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()

    # Fire pixels async
    if geo.get("is_allowed"):
        asyncio.create_task(send_fb_capi(event_data))
        asyncio.create_task(send_tiktok_events(event_data))
        asyncio.create_task(send_snap_capi(event_data))

    return {"accepted": True, "valid": bool(geo.get("is_allowed"))}

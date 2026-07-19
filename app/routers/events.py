import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import TrackingEvent
from app.schemas import EventTrackSchema
from app.services.geo import get_client_ip
from app.services.pixels import send_fb_capi, send_tiktok_events, send_snap_capi

router = APIRouter()


@router.post("/events/track", status_code=202)
async def track_event(
    payload: EventTrackSchema,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    event_data = payload.model_dump()
    ip = get_client_ip(request)
    ua = request.headers.get("user-agent", "")

    # Enrich match keys for CAPI when the browser proxy omitted them
    user_data = dict(event_data.get("user_data") or {})
    if ip and not user_data.get("client_ip_address"):
        user_data["client_ip_address"] = ip
    if ua and not user_data.get("client_user_agent"):
        user_data["client_user_agent"] = ua
    event_data["user_data"] = user_data

    event = TrackingEvent(
        id=uuid.uuid4(),
        event_name=payload.event_name,
        event_id=payload.event_id,
        event_time=payload.event_time,
        user_data=user_data,
        custom_data=payload.custom_data,
        ip_address=ip,
        created_at=datetime.utcnow(),
    )
    try:
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()

    background_tasks.add_task(send_fb_capi, event_data)
    background_tasks.add_task(send_tiktok_events, event_data)
    background_tasks.add_task(send_snap_capi, event_data)

    return {"accepted": True}

import asyncio
import uuid
from datetime import datetime
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import TrackingEvent
from app.schemas import EventTrackSchema
from app.services.pixels import send_fb_capi, send_tiktok_events, send_snap_capi

router = APIRouter()


@router.post("/events/track", status_code=202)
async def track_event(
    payload: EventTrackSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    event_data = payload.model_dump()

    # Save to DB
    event = TrackingEvent(
        id=uuid.uuid4(),
        event_name=payload.event_name,
        event_id=payload.event_id,
        event_time=payload.event_time,
        user_data=payload.user_data,
        custom_data=payload.custom_data,
        ip_address=request.client.host if request.client else None,
        created_at=datetime.utcnow(),
    )
    try:
        db.add(event)
        db.commit()
    except Exception:
        db.rollback()

    # Fire pixels async
    asyncio.create_task(send_fb_capi(event_data))
    asyncio.create_task(send_tiktok_events(event_data))
    asyncio.create_task(send_snap_capi(event_data))

    return {"accepted": True}

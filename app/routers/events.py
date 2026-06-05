import asyncio
from fastapi import APIRouter
from app.schemas import EventTrackSchema
from app.services.pixels import send_fb_capi, send_tiktok_events, send_snap_capi

router = APIRouter()


@router.post("/events/track", status_code=202)
async def track_event(payload: EventTrackSchema):
    event_data = payload.model_dump()
    asyncio.create_task(send_fb_capi(event_data))
    asyncio.create_task(send_tiktok_events(event_data))
    asyncio.create_task(send_snap_capi(event_data))
    return {"accepted": True}

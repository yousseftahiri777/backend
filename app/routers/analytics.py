import uuid
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PageView
from app.schemas import PageViewSchema
from app.services.geo import get_client_ip, require_trusted_proxy, resolve_geo

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analytics/pageview", status_code=202)
async def track_pageview(
    payload: PageViewSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    require_trusted_proxy(request)
    ip = get_client_ip(request)
    recent_count = (
        db.query(PageView)
        .filter(
            PageView.ip_address == ip,
            PageView.created_at >= datetime.utcnow() - timedelta(minutes=1),
        )
        .count()
    )
    if recent_count >= 120:
        raise HTTPException(status_code=429, detail="Too many page views")
    geo = await resolve_geo(request, ip)

    view = PageView(
        id=uuid.uuid4(),
        session_id=payload.sessionId[:128],
        path=payload.path[:512],
        referrer=(payload.referrer or "")[:512] or None,
        utm_source=(payload.utmSource or "")[:128] or None,
        utm_medium=(payload.utmMedium or "")[:128] or None,
        utm_campaign=(payload.utmCampaign or "")[:128] or None,
        ip_address=ip,
        country_code=geo.get("country_code"),
        city=geo.get("city"),
        is_vpn=bool(geo.get("is_vpn")),
        is_valid=bool(geo.get("is_allowed")),
        created_at=datetime.utcnow(),
    )
    db.add(view)
    db.commit()
    return {"accepted": True, "valid": view.is_valid}

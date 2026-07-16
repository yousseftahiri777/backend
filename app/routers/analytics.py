import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PageView
from app.schemas import PageViewSchema
from app.services.geo import get_client_ip, resolve_geo

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/analytics/pageview", status_code=202)
async def track_pageview(
    payload: PageViewSchema,
    request: Request,
    db: Session = Depends(get_db),
):
    ip = get_client_ip(request)
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

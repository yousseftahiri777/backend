import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from app.config import settings
from app.db_migrate import run_migrations
from app.routers import orders, events, contact, admin, analytics

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    try:
        run_migrations()
    except Exception as exc:
        logger.error("Startup migration failed: %s", exc)
        raise
    yield


app = FastAPI(
    title="LAMÁ API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(orders.router, prefix="/api/v1")
app.include_router(events.router, prefix="/api/v1")
app.include_router(contact.router, prefix="/api/v1")
app.include_router(analytics.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, exc: SQLAlchemyError):
    logger.error("Database error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"detail": "خطأ في قاعدة البيانات. يرجى المحاولة لاحقاً أو التواصل مع الدعم."},
    )


@app.get("/health")
async def health_check():
    return {"status": "healthy"}


def _pixel_production_status(pixel_id: str, access_token: str, test_code: str) -> dict:
    test_set = bool((test_code or "").strip())
    return {
        "pixel_id": pixel_id or None,
        "access_token_set": bool((access_token or "").strip()),
        "test_event_code_set": test_set,
        "production_mode": not test_set,
    }


@app.get("/api/v1/tiktok/status")
async def tiktok_integration_status():
    """Debug TikTok CAPI config without exposing secrets."""
    pixel = (settings.TIKTOK_PIXEL_ID or "").strip()
    token = (settings.TIKTOK_ACCESS_TOKEN or "").strip()
    test_code = (settings.TIKTOK_TEST_EVENT_CODE or "").strip()
    status = _pixel_production_status(pixel, token, test_code)
    return {
        **status,
        "pixel_id_ok": pixel == "D9L7CFJC77U3ACU27SV0",
        "ready_hint": (
            "OK for production"
            if pixel and token and status["production_mode"]
            else "Set TIKTOK_PIXEL_ID + TIKTOK_ACCESS_TOKEN and clear TIKTOK_TEST_EVENT_CODE"
        ),
    }


@app.get("/api/v1/pixels/status")
async def pixels_integration_status():
    """Debug FB + TikTok CAPI — confirm test_event_code is cleared in production."""
    fb = _pixel_production_status(
        (settings.FB_PIXEL_ID or "").strip(),
        (settings.FB_ACCESS_TOKEN or "").strip(),
        (settings.FB_TEST_EVENT_CODE or "").strip(),
    )
    tt = _pixel_production_status(
        (settings.TIKTOK_PIXEL_ID or "").strip(),
        (settings.TIKTOK_ACCESS_TOKEN or "").strip(),
        (settings.TIKTOK_TEST_EVENT_CODE or "").strip(),
    )
    return {
        "facebook": fb,
        "tiktok": {**tt, "pixel_id_ok": tt["pixel_id"] == "D9L7CFJC77U3ACU27SV0"},
        "production_ready": fb["production_mode"] and tt["production_mode"],
        "action": (
            "OK — launch campaigns"
            if fb["production_mode"] and tt["production_mode"]
            else "Clear FB_TEST_EVENT_CODE and TIKTOK_TEST_EVENT_CODE in Easypanel backend env, then restart"
        ),
    }


@app.get("/")
async def root():
    return {"service": "LAMÁ API", "status": "running"}

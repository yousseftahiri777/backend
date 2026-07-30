"""Fire-and-forget CAPI dispatch (more reliable than BackgroundTasks for async httpx)."""

import asyncio
import logging

from app.services.pixels import send_fb_capi, send_snap_capi, send_tiktok_events

logger = logging.getLogger(__name__)


def _log_pixel_task_error(platform: str, exc: BaseException) -> None:
    logger.error("%s CAPI background task failed: %s", platform, exc)


def schedule_pixel_events(event_data: dict) -> None:
    """Schedule Meta/TikTok/Snap server events on the running event loop."""

    async def _run_all() -> None:
        await asyncio.gather(
            send_tiktok_events(event_data),
            send_fb_capi(event_data),
            send_snap_capi(event_data),
            return_exceptions=True,
        )

    def _done(task: asyncio.Task) -> None:
        try:
            results = task.result()
            if isinstance(results, list):
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        platforms = ("TikTok", "Meta", "Snap")
                        _log_pixel_task_error(platforms[i], result)
        except Exception as exc:
            logger.error("CAPI task bundle failed: %s", exc)

    try:
        task = asyncio.create_task(_run_all())
        task.add_done_callback(_done)
    except RuntimeError:
        logger.error("CAPI schedule failed: no running event loop")

"""Run Alembic migrations on application startup."""

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger(__name__)

_ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def run_migrations() -> None:
    """Apply pending DB migrations (idempotent)."""
    cfg = Config(str(_ALEMBIC_INI))
    logger.info("Running database migrations...")
    command.upgrade(cfg, "head")
    logger.info("Database migrations complete.")

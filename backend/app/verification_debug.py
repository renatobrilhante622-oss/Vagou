"""Explicit test-only escape hatch; never enabled by default or in production."""
import logging

from app.config import settings

logger = logging.getLogger('uvicorn.error')


def log_verification_fallback(code: str) -> None:
    cfg = settings()
    if cfg.environment in ('development', 'test') and cfg.debug_verification_codes:
        logger.warning('verification_delivery_debug_fallback_enabled')
        print(f'DEBUG VERIFICATION CODE: {code}', flush=True)

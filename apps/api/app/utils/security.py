"""
Optional API-key authentication middleware.

Activate by setting API_KEY=<secret> in .env.
When API_KEY is empty, all requests pass through (dev mode).
"""
from __future__ import annotations

from fastapi import HTTPException, Request, status
from fastapi.security import APIKeyHeader

from app.config import get_settings

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)
settings = get_settings()


async def verify_api_key(request: Request) -> None:
    """
    FastAPI dependency — add to routers or individual routes.

    Usage in a router:
        router = APIRouter(dependencies=[Depends(verify_api_key)])
    """
    if not settings.api_key:
        # Dev mode: no key configured, allow all requests.
        return

    key = request.headers.get("X-API-Key", "")
    if key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing X-API-Key header.",
        )

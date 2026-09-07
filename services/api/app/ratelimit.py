"""Lightweight fixed-window in-memory rate limiter for a couple of endpoints.

Kept intentionally small (spec §7 only asks to rate-limit login and upload).
Uses the `limits` library directly instead of slowapi's decorator, because
slowapi's @limiter.limit wrapper confuses FastAPI <0.120's dependency parser
when the endpoint also declares UploadFile/body params.
"""
from __future__ import annotations

import time

from fastapi import HTTPException, Request, status

from limits import parse
from limits.storage import MemoryStorage
from limits.strategies import FixedWindowRateLimiter

_storage = MemoryStorage()
_rate_limiter = FixedWindowRateLimiter(_storage)


def rate_limit(limit_str: str, scope_prefix: str):
    """Return a FastAPI dependency that enforces `limit_str` per client IP."""

    async def dependency(request: Request) -> None:
        item = parse(limit_str)
        client_ip = request.client.host if request.client else "unknown"
        key = f"{scope_prefix}:{client_ip}"
        if not _rate_limiter.hit(item, key, cost=1):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Try again later.",
            )

    return dependency

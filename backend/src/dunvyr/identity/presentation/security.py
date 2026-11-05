"""Origin/CSRF and rate-limit guards for state-changing identity endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from dunvyr.identity.application.rate_limit import SlidingWindowRateLimiter
from dunvyr.identity.presentation.config import AllowedOrigins


def require_allowed_origin(request: Request) -> None:
    """Reject state-changing requests without an allow-listed ``Origin`` header."""
    allowed: AllowedOrigins = request.app.state.allowed_origins
    origin = request.headers.get("origin")
    if origin is None or not allowed.contains(origin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )


def enforce_rate_limit(request: Request) -> None:
    """Apply the primitive per-client sliding-window limiter."""
    limiter: SlidingWindowRateLimiter = request.app.state.rate_limiter
    client = request.client.host if request.client is not None else "unknown"
    retry_after = limiter.hit(client)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many session creation requests",
            headers={"Retry-After": str(retry_after)},
        )

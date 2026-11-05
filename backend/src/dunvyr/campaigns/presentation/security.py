"""Origin/CSRF and rate-limit guards for campaign-creation endpoints."""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from dunvyr.campaigns.application.rate_limit import CampaignSlidingWindowRateLimiter
from dunvyr.campaigns.presentation.config import OriginAllowList


def require_allowed_origin(request: Request) -> None:
    """Reject state-changing requests without an allow-listed ``Origin`` header."""
    allowed: OriginAllowList = request.app.state.allowed_origins
    origin = request.headers.get("origin")
    if origin is None or not allowed.contains(origin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin not allowed",
        )


def enforce_campaign_rate_limit(request: Request) -> None:
    """Apply the campaigns-specific per-client sliding-window limiter."""
    limiter: CampaignSlidingWindowRateLimiter = request.app.state.campaign_rate_limiter
    client = request.client.host if request.client is not None else "unknown"
    retry_after = limiter.hit(client)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many campaign creation requests",
            headers={"Retry-After": str(retry_after)},
        )

"""Origin/CSRF and rate-limit guards for campaign endpoints."""

from __future__ import annotations

import threading
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status

from dunvyr.campaigns.application.rate_limit import (
    CampaignRateLimitPolicy,
    CampaignSlidingWindowRateLimiter,
)
from dunvyr.campaigns.presentation.config import OriginAllowList

_join_limiter_lock = threading.Lock()


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


def _join_limiter(request: Request) -> CampaignSlidingWindowRateLimiter:
    """Build one join bucket per app lazily, separately from campaign creation."""
    state = request.app.state
    limiter: CampaignSlidingWindowRateLimiter | None = getattr(
        state,
        "campaign_join_rate_limiter",
        None,
    )
    if limiter is None:
        with _join_limiter_lock:
            limiter = getattr(state, "campaign_join_rate_limiter", None)
            if limiter is None:
                limiter = CampaignSlidingWindowRateLimiter(
                    policy=CampaignRateLimitPolicy(),
                    clock=lambda: datetime.now(UTC),
                )
                state.campaign_join_rate_limiter = limiter
    return limiter


def enforce_join_rate_limit(request: Request) -> None:
    """Apply a separate per-client bucket to invitation joins."""
    limiter = _join_limiter(request)
    client = request.client.host if request.client is not None else "unknown"
    retry_after = limiter.hit(client)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many campaign join requests",
            headers={"Retry-After": str(retry_after)},
        )

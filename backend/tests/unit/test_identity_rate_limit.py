"""Unit tests for the in-process sliding-window rate limiter."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from dunvyr.identity.application.rate_limit import (
    RateLimitPolicy,
    SlidingWindowRateLimiter,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.mark.unit
def test_default_policy_is_10_requests_per_60_seconds() -> None:
    assert RateLimitPolicy().limit == 10
    assert RateLimitPolicy().window == timedelta(seconds=60)


@pytest.mark.unit
def test_limiter_allows_requests_up_to_the_limit() -> None:
    clock = FixedClock(NOW)
    limiter = SlidingWindowRateLimiter(
        policy=RateLimitPolicy(limit=2, window=timedelta(seconds=60)),
        clock=clock,
    )

    assert limiter.hit("127.0.0.1") is None
    assert limiter.hit("127.0.0.1") is None


@pytest.mark.unit
def test_limiter_reports_retry_after_when_window_is_full() -> None:
    clock = FixedClock(NOW)
    limiter = SlidingWindowRateLimiter(
        policy=RateLimitPolicy(limit=2, window=timedelta(seconds=60)),
        clock=clock,
    )
    limiter.hit("client")
    limiter.hit("client")

    assert limiter.hit("client") == 60

    clock.now += timedelta(seconds=30)
    assert limiter.hit("client") == 30

    clock.now += timedelta(seconds=31)
    assert limiter.hit("client") is None


@pytest.mark.unit
def test_limiter_tracks_clients_independently() -> None:
    clock = FixedClock(NOW)
    limiter = SlidingWindowRateLimiter(
        policy=RateLimitPolicy(limit=1, window=timedelta(seconds=60)),
        clock=clock,
    )

    assert limiter.hit("first") is None
    assert limiter.hit("first") == 60
    assert limiter.hit("second") is None

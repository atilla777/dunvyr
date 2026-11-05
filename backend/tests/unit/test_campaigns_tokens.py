"""Unit tests for the invitation-secret generator and limiter policy."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

import pytest

from dunvyr.campaigns.application.rate_limit import (
    CampaignRateLimitPolicy,
    CampaignSlidingWindowRateLimiter,
)
from dunvyr.campaigns.infrastructure.tokens import SecretsInvitationSecretGenerator

URL_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_-]+")
NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


@pytest.mark.unit
def test_generator_returns_256_bit_url_safe_invitation_secrets() -> None:
    secret = SecretsInvitationSecretGenerator().generate()

    assert len(secret) == 43
    assert URL_SAFE_TOKEN.fullmatch(secret)


@pytest.mark.unit
def test_generator_produces_unique_unpredictable_secrets() -> None:
    generator = SecretsInvitationSecretGenerator()

    secrets = {generator.generate() for _ in range(500)}

    assert len(secrets) == 500


@pytest.mark.unit
def test_campaign_rate_limit_defaults_match_the_identity_bucket() -> None:
    policy = CampaignRateLimitPolicy()

    assert policy.limit == 10
    assert policy.window == timedelta(seconds=60)


@pytest.mark.unit
def test_campaign_rate_limiter_enforces_its_own_bucket() -> None:
    clock = FixedClock(NOW)
    limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(limit=1, window=timedelta(seconds=60)),
        clock=clock,
    )

    assert limiter.hit("127.0.0.1") is None
    assert limiter.hit("127.0.0.1") == 60
    assert limiter.hit("192.168.1.10") is None

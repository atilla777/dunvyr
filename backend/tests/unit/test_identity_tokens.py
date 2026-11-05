"""Unit tests for the opaque session-token generator."""

from __future__ import annotations

import re

import pytest

from dunvyr.identity.infrastructure.tokens import SecretsTokenGenerator

URL_SAFE_TOKEN = re.compile(r"[A-Za-z0-9_-]+")


@pytest.mark.unit
def test_generator_returns_256_bit_url_safe_tokens() -> None:
    # secrets.token_urlsafe(32) encodes 32 random bytes as 43 URL-safe characters.
    token = SecretsTokenGenerator().generate()

    assert len(token) == 43
    assert URL_SAFE_TOKEN.fullmatch(token)


@pytest.mark.unit
def test_generator_produces_unique_unpredictable_tokens() -> None:
    generator = SecretsTokenGenerator()

    tokens = {generator.generate() for _ in range(500)}

    assert len(tokens) == 500

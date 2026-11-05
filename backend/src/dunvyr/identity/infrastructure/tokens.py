"""Opaque session-token generation using the operating system CSPRNG."""

from __future__ import annotations

import secrets

SESSION_TOKEN_BYTES = 32


class SecretsTokenGenerator:
    """Produce 256-bit URL-safe opaque tokens with ``secrets``."""

    def generate(self) -> str:
        return secrets.token_urlsafe(SESSION_TOKEN_BYTES)

"""Campaign invitation secret generation using the operating system CSPRNG."""

from __future__ import annotations

import secrets

from dunvyr.campaigns.domain.invitation import INVITATION_SECRET_BYTES


class SecretsInvitationSecretGenerator:
    """Produce 256-bit URL-safe invitation secrets with ``secrets``."""

    def generate(self) -> str:
        return secrets.token_urlsafe(INVITATION_SECRET_BYTES)

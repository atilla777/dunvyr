"""Invitation value object: only a SHA-256 hash of the bearer secret is kept."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, replace

INVITATION_SECRET_BYTES = 32

_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


class InvalidInvitation(ValueError):
    """Raised when an invitation violates its invariants."""


def hash_invitation_secret(secret: str) -> str:
    """Return the SHA-256 hex digest stored for an invitation bearer secret."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class Invitation:
    """A single revocable campaign invitation.

    The raw secret never lives in this object: persistence only ever sees the
    hash, so a database leak cannot be replayed as an invitation credential.
    """

    token_hash: str
    revoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.token_hash, str) or _SHA256_HEX.fullmatch(self.token_hash) is None:
            raise InvalidInvitation("Invitation must store a lowercase SHA-256 hex digest")
        if not isinstance(self.revoked, bool):
            raise InvalidInvitation("Invitation revocation flag must be a boolean")

    @classmethod
    def issue(cls, secret: str) -> Invitation:
        """Hash a freshly generated raw secret; the raw value is not retained."""
        if not isinstance(secret, str) or not secret:
            raise InvalidInvitation("Invitation secret must be a non-empty string")
        return cls(token_hash=hash_invitation_secret(secret))

    @property
    def is_active(self) -> bool:
        return not self.revoked

    def revoke(self) -> Invitation:
        """Return a revoked copy; the original immutable value is unchanged."""
        return replace(self, revoked=True)

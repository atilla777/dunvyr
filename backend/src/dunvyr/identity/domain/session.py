"""Server-side guest session with a fixed lifetime and a hashed opaque token.

The raw token only ever exists in the browser cookie and in the HTTP response
that sets it. Persistence stores a SHA-256 hash, so a database leak cannot be
replayed as a credential.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from dunvyr.identity.domain.guest import require_aware

SESSION_LIFETIME = timedelta(days=30)


def hash_session_token(token: str) -> str:
    """Return the SHA-256 hex digest stored for an opaque session token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class GuestSession:
    id: UUID
    guest_id: UUID
    token_hash: str
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.created_at, "created_at")
        require_aware(self.expires_at, "expires_at")
        if self.expires_at <= self.created_at:
            raise ValueError("expires_at must be after created_at")

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        guest_id: UUID,
        token_hash: str,
        created_at: datetime,
        lifetime: timedelta = SESSION_LIFETIME,
    ) -> GuestSession:
        """Create a session whose expiry is fixed at creation time."""
        require_aware(created_at, "created_at")
        return cls(
            id=id,
            guest_id=guest_id,
            token_hash=token_hash,
            created_at=created_at,
            expires_at=created_at + lifetime,
        )

    def is_valid_at(self, now: datetime) -> bool:
        """An expired session is treated exactly like a missing one."""
        require_aware(now, "now")
        return now < self.expires_at

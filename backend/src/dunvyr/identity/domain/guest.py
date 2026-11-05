"""Guest entity: an identity a browser gets after choosing a nickname."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from dunvyr.identity.domain.nickname import Nickname


def require_aware(value: datetime, field: str) -> None:
    """Reject naive datetimes: identity clocks are always timezone-aware."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class Guest:
    id: UUID
    nickname: Nickname
    created_at: datetime

    def __post_init__(self) -> None:
        require_aware(self.created_at, "created_at")

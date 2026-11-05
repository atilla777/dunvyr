"""Timezone guard shared by campaigns domain objects."""

from __future__ import annotations

from datetime import datetime


def require_aware(value: datetime, field: str) -> None:
    """Reject naive datetimes: campaigns clocks are always timezone-aware."""
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")

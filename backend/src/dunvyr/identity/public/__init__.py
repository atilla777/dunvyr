"""Public identity contract for other bounded contexts (e.g. campaigns)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

SESSION_COOKIE_NAME = "dunvyr_session"
"""Name of the HttpOnly session cookie other contexts may read."""


@dataclass(frozen=True, slots=True)
class GuestSnapshot:
    """Stable, ORM-free view of the currently authenticated guest."""

    id: UUID
    nickname: str


@runtime_checkable
class GuestResolver(Protocol):
    """Resolve a raw session token to a guest snapshot, or ``None``."""

    def resolve_guest(self, session_token: str | None) -> GuestSnapshot | None: ...


__all__ = ["SESSION_COOKIE_NAME", "GuestResolver", "GuestSnapshot"]

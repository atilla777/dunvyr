"""HTTP-boundary configuration for campaigns."""

from __future__ import annotations

from typing import Protocol

INVITATION_PATH_PREFIX = "/join/"


class OriginAllowList(Protocol):
    """Structural view of the shared origin allow-list configured by the root."""

    def contains(self, origin: str) -> bool: ...

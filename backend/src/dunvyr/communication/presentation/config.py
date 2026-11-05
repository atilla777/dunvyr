"""HTTP/WebSocket-boundary configuration for communication."""

from __future__ import annotations

from typing import Protocol


class OriginAllowList(Protocol):
    """Structural view of the shared origin allow-list configured by the root."""

    def contains(self, origin: str) -> bool: ...


__all__ = ["OriginAllowList"]

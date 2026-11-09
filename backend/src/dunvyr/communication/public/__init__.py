"""Communication public contracts, independent of concrete delivery adapters."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID


class ProposalNotifier(Protocol):
    """Post-commit, content-free invalidation for one campaign member."""

    def notify(self, campaign_id: UUID, actor_id: UUID) -> None: ...


class CheckEventStager(Protocol):
    def stage(
        self, campaign_id: UUID, result: dict[str, object], now: datetime, facts: tuple[str, ...]
    ) -> UUID: ...


__all__ = ["CheckEventStager", "ProposalNotifier"]

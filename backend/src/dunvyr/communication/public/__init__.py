"""Communication public contracts, independent of concrete delivery adapters."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class ProposalNotifier(Protocol):
    """Post-commit, content-free invalidation for one campaign member."""

    def notify(self, campaign_id: UUID, actor_id: UUID) -> None: ...


__all__ = ["ProposalNotifier"]

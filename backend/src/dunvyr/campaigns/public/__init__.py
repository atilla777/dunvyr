"""Campaigns public contract consumed by other bounded contexts.

Only ORM-free, immutable snapshots and Protocols live here. Implementations
remain inside the campaigns infrastructure/composition root, so consumers never
import campaigns inner layers or write campaigns tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class CampaignMemberSnapshot:
    """Stable view of one campaign member for cross-context consumers."""

    guest_id: UUID
    nickname: str
    role: str
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class CampaignSnapshot:
    """Stable view of a campaign roster for cross-context consumers."""

    id: UUID
    organizer_id: UUID
    members: tuple[CampaignMemberSnapshot, ...]

    def member(self, guest_id: UUID) -> CampaignMemberSnapshot | None:
        return next((member for member in self.members if member.guest_id == guest_id), None)


class CampaignMembershipReader(Protocol):
    """Resolve one membership without exposing campaigns repositories or tables."""

    def find_member(
        self,
        campaign_id: UUID,
        guest_id: UUID,
    ) -> CampaignMemberSnapshot | None: ...


class CampaignEventPublisher(Protocol):
    """Post-commit port for campaign facts other contexts deliver in real time.

    Implementations must be invoked only after the campaigns transaction has
    committed, and must never be able to roll that transaction back.
    """

    def member_joined(
        self,
        campaign_id: UUID,
        member: CampaignMemberSnapshot,
    ) -> None: ...


__all__ = [
    "CampaignEventPublisher",
    "CampaignMemberSnapshot",
    "CampaignMembershipReader",
    "CampaignSnapshot",
]

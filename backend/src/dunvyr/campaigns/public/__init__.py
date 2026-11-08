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


@dataclass(frozen=True, slots=True)
class PresenceState:
    epoch: UUID
    revision: int
    online_guest_ids: tuple[UUID, ...]


class PresencePublisher(Protocol):
    def publish(self, campaign_id: UUID, state: PresenceState) -> None: ...


class PresenceObserver(Protocol):
    def connect(self, campaign_id: UUID, guest_id: UUID, connection_id: UUID) -> None: ...
    def disconnect(self, connection_id: UUID) -> None: ...
    def renew(self, connection_id: UUID) -> bool: ...


class PresenceReader(Protocol):
    def read(self, campaign_id: UUID) -> PresenceState: ...


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
    "GameSessionChanged",
    "GameSessionEventStager",
    "GameSessionNotifier",
    "GameSessionReader",
    "GameSessionSnapshot",
    "GameSessionState",
    "PresenceObserver",
    "PresencePublisher",
    "PresenceReader",
    "PresenceState",
]


@dataclass(frozen=True, slots=True)
class GameSessionSnapshot:
    id: UUID
    status: str
    started_at: datetime
    ended_at: datetime | None


@dataclass(frozen=True, slots=True)
class GameSessionState:
    revision: int
    session: GameSessionSnapshot | None


@dataclass(frozen=True, slots=True)
class GameSessionChanged:
    campaign_id: UUID
    state: GameSessionState
    occurred_at: datetime


class GameSessionReader(Protocol):
    def read(self, campaign_id: UUID) -> GameSessionState: ...


class GameSessionEventStager(Protocol):
    """Stage only, within the caller's transaction; never commit or deliver."""

    def stage(self, fact: GameSessionChanged) -> UUID: ...


class GameSessionNotifier(Protocol):
    """Deliver an already committed event; failures cannot undo persistence."""

    def notify(self, campaign_id: UUID, event_id: UUID) -> None: ...

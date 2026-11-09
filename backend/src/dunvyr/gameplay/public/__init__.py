"""Immutable, safe gameplay projection and explicit transaction participants."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Participant:
    guest_id: str
    character_id: str


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    encounter_id: str
    participants: tuple[Participant, ...]
    round_order: tuple[str, ...]
    round_number: int
    cursor: int
    skipped: tuple[str, ...]
    current_guest_id: str | None


@dataclass(frozen=True, slots=True)
class QueueState:
    version: int
    queue: QueueSnapshot | None


class QueueReader(Protocol):
    def read(self, campaign_id: UUID) -> QueueState: ...


class QueueEventStager(Protocol):
    def stage(self, campaign_id: UUID, state: QueueState, now: datetime) -> UUID: ...


class QueueNotifier(Protocol):
    def notify(self, campaign_id: UUID, event_id: UUID) -> None: ...

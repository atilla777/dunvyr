"""Pure lifecycle of a single synchronous campaign meeting."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from uuid import UUID


class GameSessionStatus(StrEnum):
    RUNNING = "running"
    PAUSED = "paused"
    ENDED = "ended"


class InvalidGameSessionAction(ValueError):
    """The requested action is not valid in the current state."""


@dataclass(frozen=True, slots=True)
class GameSession:
    id: UUID
    campaign_id: UUID
    status: GameSessionStatus

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID) or not isinstance(self.campaign_id, UUID):
            raise ValueError("Session and campaign ids must be UUIDs")
        if not isinstance(self.status, GameSessionStatus):
            raise ValueError("Invalid game session status")

    @classmethod
    def start(cls, *, id: UUID, campaign_id: UUID) -> GameSession:
        return cls(id=id, campaign_id=campaign_id, status=GameSessionStatus.RUNNING)

    def transition(self, action: str) -> GameSession:
        transitions = {
            (GameSessionStatus.RUNNING, "pause"): GameSessionStatus.PAUSED,
            (GameSessionStatus.RUNNING, "end"): GameSessionStatus.ENDED,
            (GameSessionStatus.PAUSED, "resume"): GameSessionStatus.RUNNING,
            (GameSessionStatus.PAUSED, "end"): GameSessionStatus.ENDED,
        }
        status = transitions.get((self.status, action))
        if status is None:
            raise InvalidGameSessionAction("Invalid game session transition")
        return replace(self, status=status)

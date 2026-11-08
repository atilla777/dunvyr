"""Lifecycle orchestration with a single atomic multi-context transaction."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from dunvyr.campaigns.application.ports import Clock, IdFactory
from dunvyr.campaigns.domain.game_session import (
    GameSession,
    GameSessionStatus,
    InvalidGameSessionAction,
)
from dunvyr.campaigns.public import (
    GameSessionChanged,
    GameSessionEventStager,
    GameSessionNotifier,
    GameSessionSnapshot,
    GameSessionState,
)

logger = logging.getLogger(__name__)


class SessionConflict(ValueError):
    pass


@dataclass(frozen=True)
class SessionCommand:
    campaign_id: UUID
    actor_id: UUID
    key: UUID
    expected_revision: int
    action: str
    session_id: UUID | None = None

    def payload(self) -> str:
        return f"{self.action}:{self.session_id}:{self.expected_revision}"


class SessionUnitOfWork(Protocol):
    def lock(self, campaign_id: UUID) -> None: ...
    def authorize(self, campaign_id: UUID, actor_id: UUID, *, organizer: bool) -> None: ...
    def read(self, campaign_id: UUID) -> GameSessionState: ...
    def receipt(self, command: SessionCommand) -> tuple[str, GameSessionState] | None: ...
    def save(self, command: SessionCommand, state: GameSessionState) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class GameSessionService:
    def __init__(
        self,
        uow: SessionUnitOfWork,
        stager: GameSessionEventStager,
        notifier: GameSessionNotifier,
        clock: Clock,
        ids: IdFactory,
    ) -> None:
        self.uow, self.stager, self.notifier = uow, stager, notifier
        self.clock, self.ids = clock, ids

    def get(self, campaign_id: UUID, actor_id: UUID) -> GameSessionState:
        self.uow.authorize(campaign_id, actor_id, organizer=False)
        return self.uow.read(campaign_id)

    def execute(self, command: SessionCommand) -> tuple[GameSessionState, bool]:
        try:
            # A database write lock precedes receipt/state reads. Independent
            # connections serialize without upgrading stale read snapshots.
            self.uow.lock(command.campaign_id)
            self.uow.authorize(command.campaign_id, command.actor_id, organizer=True)
            receipt = self.uow.receipt(command)
            if receipt is not None:
                payload, original = receipt
                if payload != command.payload():
                    raise SessionConflict("conflict")
                self.uow.rollback()
                return original, True
            current = self.uow.read(command.campaign_id)
            if current.revision != command.expected_revision:
                raise SessionConflict("stale_state")
            now = self.clock()
            session = self._transition(command, current, now)
            state = GameSessionState(current.revision + 1, session)
            self.uow.save(command, state)
            event_id = self.stager.stage(GameSessionChanged(command.campaign_id, state, now))
            self.uow.commit()
        except Exception:
            self.uow.rollback()
            raise
        try:
            self.notifier.notify(command.campaign_id, event_id)
        except Exception:
            logger.warning("Game session delivery failed after commit", exc_info=True)
        return state, False

    def _transition(
        self, command: SessionCommand, current: GameSessionState, now: datetime
    ) -> GameSessionSnapshot:
        previous = current.session
        if command.action == "start":
            if previous is not None and previous.status != "ended":
                raise InvalidGameSessionAction("An active session already exists")
            session = GameSession.start(id=self.ids(), campaign_id=command.campaign_id)
            return GameSessionSnapshot(session.id, session.status.value, now, None)
        if previous is None or previous.id != command.session_id:
            raise InvalidGameSessionAction("Session is not current")
        session = GameSession(previous.id, command.campaign_id, GameSessionStatus(previous.status))
        changed = session.transition(command.action)
        return GameSessionSnapshot(
            previous.id,
            changed.status.value,
            previous.started_at,
            now if changed.status == GameSessionStatus.ENDED else None,
        )

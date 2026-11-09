"""Single transaction orchestration; foreign data only through owner public ports."""

import json
import logging
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from typing import Protocol
from uuid import UUID

from dunvyr.adventures.public import AvailableEncounterCatalogReader
from dunvyr.campaigns.public import CampaignGameplayAccess, GuardedPresenceReader
from dunvyr.characters.public import CharacterEligibilityReader
from dunvyr.gameplay.domain import Queue, start_queue
from dunvyr.gameplay.public import (
    Participant,
    QueueEventStager,
    QueueNotifier,
    QueueSnapshot,
    QueueState,
)

logger = logging.getLogger(__name__)


class QueueError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status, self.detail = status, detail


@dataclass(frozen=True)
class QueueCommand:
    campaign_id: UUID
    actor_id: UUID
    key: UUID
    expected_version: int
    expected_lifecycle_revision: int
    action: str
    character_id: UUID | None = None
    encounter_id: str | None = None
    target_guest_id: UUID | None = None

    def payload(self) -> str:
        return json.dumps(asdict(self), default=str, sort_keys=True)


def project(encounter_id: str, queue: Queue) -> QueueState:
    return QueueState(
        queue.version,
        QueueSnapshot(
            encounter_id,
            tuple(Participant(*p) for p in queue.base_order),
            queue.round_order,
            queue.round_number,
            queue.cursor,
            queue.skipped,
            queue.current,
        ),
    )


class QueueUnitOfWork(Protocol):
    def load(self, campaign_id: UUID) -> tuple[str, Queue] | None: ...
    def read(self, campaign_id: UUID) -> QueueState: ...
    def receipt(self, command: QueueCommand) -> tuple[str, QueueState] | None: ...
    def save(self, campaign_id: UUID, encounter_id: str, queue: Queue, expected: int) -> None: ...
    def record(self, command: QueueCommand, state: QueueState) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


class QueueService:
    def __init__(
        self,
        uow: QueueUnitOfWork,
        campaigns: CampaignGameplayAccess,
        characters: CharacterEligibilityReader,
        catalog: AvailableEncounterCatalogReader,
        stager: QueueEventStager,
        notifier: QueueNotifier,
        clock: Callable[[], datetime],
        presence: GuardedPresenceReader,
    ) -> None:
        self.uow, self.campaigns, self.characters, self.catalog = (
            uow,
            campaigns,
            characters,
            catalog,
        )
        self.stager, self.notifier, self.clock = stager, notifier, clock
        self.presence = presence

    def authorize(self, campaign_id: UUID, actor_id: UUID) -> None:
        if not any(m.guest_id == actor_id for m in self.campaigns.roster(campaign_id)):
            raise QueueError(403, "forbidden")

    def get(self, campaign_id: UUID, actor_id: UUID) -> QueueState:
        self.authorize(campaign_id, actor_id)
        return self.uow.read(campaign_id)

    def reconcile(self, campaign_id: UUID) -> None:
        event_id = None
        try:
            self.campaigns.lock(campaign_id)
            lifecycle = self.campaigns.read(campaign_id)
            current = self.uow.load(campaign_id)
            if (
                current is None
                or lifecycle.session is None
                or lifecycle.session.status != "running"
            ):
                self.uow.rollback()
                return
            encounter_id, queue = current
            now = self.clock()
            with self.presence.guard(campaign_id) as presence:
                normalized = queue.normalize({str(g) for g in presence.online_guest_ids})
                if normalized != queue:
                    self.uow.save(campaign_id, encounter_id, normalized, queue.version)
                    event_id = self.stager.stage(
                        campaign_id, project(encounter_id, normalized), now
                    )
                self.uow.commit()
        except BaseException:
            self.uow.rollback()
            raise
        if event_id is not None:
            self.notify(campaign_id, event_id)

    def execute(self, command: QueueCommand) -> tuple[QueueState, bool]:
        try:
            self.campaigns.lock(command.campaign_id)
            self.authorize(command.campaign_id, command.actor_id)
            receipt = self.uow.receipt(command)
            if receipt:
                if receipt[0] != command.payload():
                    raise QueueError(409, "conflict")
                self.uow.rollback()
                return receipt[1], True
            lifecycle = self.campaigns.read(command.campaign_id)
            if lifecycle.revision != command.expected_lifecycle_revision:
                raise QueueError(409, "stale_lifecycle")
            if lifecycle.session is None or lifecycle.session.status != "running":
                raise QueueError(409, "meeting_not_running")
            current = self.uow.load(command.campaign_id)
            if command.expected_version != (current[1].version if current else 0):
                raise QueueError(409, "stale_state")
            if command.action == "swap":
                if current is None:
                    raise QueueError(409, "invalid_action")
                encounter_id, queue = current
                now = self.clock()
                with self.presence.guard(command.campaign_id) as presence:
                    online = {str(g) for g in presence.online_guest_ids}
                    try:
                        queue = queue.swap(
                            str(command.actor_id), str(command.target_guest_id), online
                        )
                    except ValueError as error:
                        raise QueueError(409, "invalid_swap") from error
                    state = project(encounter_id, queue)
                    self.uow.save(
                        command.campaign_id, encounter_id, queue, command.expected_version
                    )
                    event_id = self.stager.stage(command.campaign_id, state, now)
                    self.uow.record(command, state)
                    self.uow.commit()
                self.notify(command.campaign_id, event_id)
                return state, False
            if current is not None or command.action != "start":
                raise QueueError(409, "invalid_action")
            own = self.characters.eligible(command.campaign_id, command.actor_id)
            if own is None or own.id != command.character_id:
                raise QueueError(403, "invalid_character")
            catalog = self.catalog.available_encounters(command.campaign_id)
            if catalog is None or not any(e.id == command.encounter_id for e in catalog.encounters):
                raise QueueError(409, "encounter_unavailable")
            roster = self.campaigns.roster(command.campaign_id)
            participants = tuple(
                (str(m.guest_id), str(c.id))
                for m in roster
                if (c := self.characters.eligible(command.campaign_id, m.guest_id))
            )
            queue = start_queue(participants)
            assert command.encounter_id is not None
            now = self.clock()
            with self.presence.guard(command.campaign_id) as presence:
                queue = replace(
                    queue.normalize({str(g) for g in presence.online_guest_ids}), version=1
                )
                state = project(command.encounter_id, queue)
                self.uow.save(command.campaign_id, command.encounter_id, queue, 0)
                event_id = self.stager.stage(command.campaign_id, state, now)
                self.uow.record(command, state)
                self.uow.commit()
        except BaseException:
            self.uow.rollback()
            raise
        self.notify(command.campaign_id, event_id)
        return state, False

    def notify(self, campaign_id: UUID, event_id: UUID) -> None:
        try:
            self.notifier.notify(campaign_id, event_id)
        except Exception:
            logger.warning("Queue notification failed after commit", exc_info=True)

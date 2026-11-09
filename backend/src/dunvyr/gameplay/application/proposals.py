"""Private proposal commands, coordinated within the campaign writer transaction."""

import json
import logging
from dataclasses import asdict, dataclass
from typing import Protocol
from uuid import UUID, uuid4

from dunvyr.adventures.public import AvailableEncounterCatalog, AvailableEncounterCatalogReader
from dunvyr.campaigns.public import CampaignGameplayAccess, GuardedPresenceReader
from dunvyr.characters.public import CharacterEligibilityReader
from dunvyr.communication.public import ProposalNotifier
from dunvyr.gameplay.application.service import QueueError
from dunvyr.gameplay.domain import ProposalCollection, ProposedAction, Queue

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Selection:
    encounter_id: str
    object_id: str
    solution_id: str
    encounter_name: str
    solution_name: str


@dataclass(frozen=True)
class ProposalView:
    id: str
    character_id: str
    selection: Selection | None
    availability: str


@dataclass(frozen=True)
class ProposalState:
    version: int
    proposals: tuple[ProposalView, ...]


@dataclass(frozen=True)
class ProposalCommand:
    campaign_id: UUID
    actor_id: UUID
    key: UUID
    expected_version: int
    expected_queue_version: int
    expected_lifecycle_revision: int
    action: str
    proposal_id: UUID | None = None
    character_id: UUID | None = None
    encounter_id: str | None = None
    object_id: str | None = None
    solution_id: str | None = None

    def payload(self) -> str:
        return json.dumps(asdict(self), default=str, sort_keys=True)


class ProposalUnitOfWork(Protocol):
    def load(self, campaign_id: UUID, actor_id: UUID) -> ProposalCollection: ...
    def queue(self, campaign_id: UUID) -> Queue | None: ...
    def receipt(self, command: ProposalCommand) -> tuple[str, ProposalState] | None: ...
    def save(self, campaign_id: UUID, collection: ProposalCollection, expected: int) -> None: ...
    def record(self, command: ProposalCommand, state: ProposalState) -> None: ...
    def commit(self) -> None: ...
    def rollback(self) -> None: ...


def selection_for(
    catalog: AvailableEncounterCatalog | None, encounter_id: str, object_id: str, solution_id: str
) -> Selection | None:
    if catalog is None:
        return None
    for encounter in catalog.encounters:
        if encounter.id == encounter_id and encounter.object_id == object_id:
            for solution in encounter.solutions:
                if solution.id == solution_id:
                    return Selection(
                        encounter_id, object_id, solution_id, encounter.name, solution.name
                    )
    return None


def project(
    collection: ProposalCollection, catalog: AvailableEncounterCatalog | None
) -> ProposalState:
    def view(proposal: ProposedAction) -> ProposalView:
        selection = None
        if catalog is not None and catalog.fingerprint == proposal.fingerprint:
            selection = selection_for(
                catalog, proposal.encounter_id, proposal.object_id, proposal.solution_id
            )
        return ProposalView(
            proposal.id,
            proposal.character_id,
            selection,
            "available" if selection else "unavailable",
        )

    return ProposalState(collection.version, tuple(view(p) for p in collection.pending))


class ProposalService:
    def __init__(
        self,
        uow: ProposalUnitOfWork,
        campaigns: CampaignGameplayAccess,
        characters: CharacterEligibilityReader,
        catalog: AvailableEncounterCatalogReader,
        presence: GuardedPresenceReader,
        notifier: ProposalNotifier,
    ) -> None:
        self.uow, self.campaigns, self.characters = uow, campaigns, characters
        self.catalog, self.presence, self.notifier = catalog, presence, notifier

    def authorize(self, campaign_id: UUID, actor_id: UUID) -> None:
        if not any(m.guest_id == actor_id for m in self.campaigns.roster(campaign_id)):
            raise QueueError(403, "forbidden")

    def get(self, campaign_id: UUID, actor_id: UUID) -> ProposalState:
        try:
            self.campaigns.lock(campaign_id)
            self.authorize(campaign_id, actor_id)
            return project(
                self.uow.load(campaign_id, actor_id), self.catalog.available_encounters(campaign_id)
            )
        finally:
            self.uow.rollback()

    def execute(self, command: ProposalCommand) -> tuple[ProposalState, bool]:
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
            queue = self.uow.queue(command.campaign_id)
            if (queue.version if queue else 0) != command.expected_queue_version:
                raise QueueError(409, "stale_queue")
            collection = self.uow.load(command.campaign_id, command.actor_id)
            if collection.version != command.expected_version:
                raise QueueError(409, "stale_state")
            catalog = self.catalog.available_encounters(command.campaign_id)
            if command.action == "create":
                own = self.characters.eligible(command.campaign_id, command.actor_id)
                if own is None or own.id != command.character_id:
                    raise QueueError(403, "invalid_character")
                self._validate_selection(command, catalog)
                assert catalog is not None and command.character_id is not None
                collection = collection.create(
                    proposal_id=str(uuid4()),
                    actor=str(command.actor_id),
                    character_id=str(command.character_id),
                    encounter_id=command.encounter_id or "",
                    object_id=command.object_id or "",
                    solution_id=command.solution_id or "",
                    fingerprint=catalog.fingerprint,
                )
                state = project(collection, catalog)
                self._save(command, collection, state)
            else:
                with self.presence.guard(command.campaign_id) as presence:
                    actor = str(command.actor_id)
                    if (
                        queue is None
                        or queue.current != actor
                        or command.actor_id not in presence.online_guest_ids
                    ):
                        raise QueueError(409, "not_your_turn")
                    proposal = next(
                        (p for p in collection.pending if p.id == str(command.proposal_id)), None
                    )
                    if proposal is None:
                        raise QueueError(404, "not_found")
                    if (actor, proposal.character_id) not in queue.base_order:
                        raise QueueError(409, "invalid_character")
                    if command.action == "edit":
                        own = self.characters.eligible(command.campaign_id, command.actor_id)
                        if own is None or str(own.id) != proposal.character_id:
                            raise QueueError(403, "invalid_character")
                        self._validate_selection(command, catalog)
                        assert catalog is not None
                        collection = collection.edit(
                            str(command.proposal_id),
                            actor,
                            actor,
                            proposal.character_id,
                            command.encounter_id or "",
                            command.object_id or "",
                            command.solution_id or "",
                            catalog.fingerprint,
                        )
                    elif command.action == "cancel":
                        collection = collection.cancel(str(command.proposal_id), actor, actor)
                    else:
                        raise QueueError(409, "invalid_action")
                    state = project(collection, catalog)
                    self._save(command, collection, state)
        except ValueError as error:
            self.uow.rollback()
            raise QueueError(409, "invalid_action") from error
        except BaseException:
            self.uow.rollback()
            raise
        try:
            self.notifier.notify(command.campaign_id, command.actor_id)
        except Exception:
            logger.warning("Proposal notification failed after commit", exc_info=True)
        return state, False

    def _save(
        self, command: ProposalCommand, collection: ProposalCollection, state: ProposalState
    ) -> None:
        self.uow.save(command.campaign_id, collection, command.expected_version)
        self.uow.record(command, state)
        self.uow.commit()

    @staticmethod
    def _validate_selection(
        command: ProposalCommand, catalog: AvailableEncounterCatalog | None
    ) -> None:
        if (
            selection_for(
                catalog,
                command.encounter_id or "",
                command.object_id or "",
                command.solution_id or "",
            )
            is None
        ):
            raise QueueError(409, "selection_unavailable")

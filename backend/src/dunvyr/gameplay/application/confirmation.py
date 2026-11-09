"""One locked transaction resolves an owned, currently available proposal."""

import logging
from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from dunvyr.adventures.public import AdventureCheckParticipant, AvailableEncounterCatalogReader
from dunvyr.campaigns.public import CampaignGameplayAccess, GuardedPresenceReader
from dunvyr.characters.public import CharacterCheckInputReader
from dunvyr.communication.public import CheckEventStager
from dunvyr.gameplay.application.proposals import ProposalCommand, ProposalUnitOfWork
from dunvyr.gameplay.application.service import QueueError, QueueUnitOfWork
from dunvyr.gameplay.domain import resolve_noncombat_check
from dunvyr.gameplay.public import QueueNotifier

logger = logging.getLogger(__name__)


class CheckRepository(Protocol):
    def receipt(self, command: ProposalCommand) -> tuple[str, dict[str, object]] | None: ...
    def record(
        self, command: ProposalCommand, audit: dict[str, object], result: dict[str, object]
    ) -> None: ...
    def latest(self, campaign_id: UUID) -> dict[str, object] | None: ...


class ConfirmationService:
    def __init__(
        self,
        proposals: ProposalUnitOfWork,
        queues: QueueUnitOfWork,
        checks: CheckRepository,
        campaigns: CampaignGameplayAccess,
        characters: CharacterCheckInputReader,
        catalog: AvailableEncounterCatalogReader,
        adventures: AdventureCheckParticipant,
        presence: GuardedPresenceReader,
        stager: CheckEventStager,
        notifier: QueueNotifier,
        clock: Callable[[], datetime],
        roller: Callable[[], tuple[int, ...]],
    ) -> None:
        self.proposals, self.queues, self.checks = proposals, queues, checks
        self.campaigns, self.characters, self.catalog, self.adventures = (
            campaigns,
            characters,
            catalog,
            adventures,
        )
        self.presence, self.stager, self.notifier, self.clock, self.roller = (
            presence,
            stager,
            notifier,
            clock,
            roller,
        )

    def authorize(self, campaign_id: UUID, actor_id: UUID) -> None:
        if not any(m.guest_id == actor_id for m in self.campaigns.roster(campaign_id)):
            raise QueueError(403, "forbidden")

    def latest(self, campaign_id: UUID, actor_id: UUID) -> dict[str, object] | None:
        self.authorize(campaign_id, actor_id)
        return self.checks.latest(campaign_id)

    def execute(self, command: ProposalCommand) -> tuple[dict[str, object], bool]:
        try:
            self.campaigns.lock(command.campaign_id)
            self.authorize(command.campaign_id, command.actor_id)
            receipt = self.checks.receipt(command)
            if receipt:
                if receipt[0] != command.payload() or "result" not in receipt[1]:
                    raise QueueError(409, "conflict")
                self.proposals.rollback()
                return receipt[1]["result"], True  # type: ignore[return-value]
            lifecycle = self.campaigns.read(command.campaign_id)
            if lifecycle.revision != command.expected_lifecycle_revision:
                raise QueueError(409, "stale_lifecycle")
            if lifecycle.session is None or lifecycle.session.status != "running":
                raise QueueError(409, "meeting_not_running")
            current = self.queues.load(command.campaign_id)
            if current is None or current[1].version != command.expected_queue_version:
                raise QueueError(409, "stale_queue")
            encounter_id, queue = current
            collection = self.proposals.load(command.campaign_id, command.actor_id)
            if collection.version != command.expected_version:
                raise QueueError(409, "stale_state")
            proposal = next(
                (p for p in collection.pending if p.id == str(command.proposal_id)), None
            )
            if proposal is None:
                raise QueueError(404, "not_found")
            if (
                proposal.encounter_id != encounter_id
                or (str(command.actor_id), proposal.character_id) not in queue.base_order
            ):
                raise QueueError(409, "invalid_action")
            catalog = self.catalog.available_encounters(command.campaign_id)
            selection = next(
                (
                    s
                    for e in (catalog.encounters if catalog else ())
                    if e.id == proposal.encounter_id and e.object_id == proposal.object_id
                    for s in e.solutions
                    if s.id == proposal.solution_id
                ),
                None,
            )
            if catalog is None or catalog.fingerprint != proposal.fingerprint or selection is None:
                raise QueueError(409, "selection_unavailable")
            if selection.check.difficulty != 5:
                raise QueueError(409, "unsupported_check")
            inputs = self.characters.check_input(
                command.campaign_id,
                command.actor_id,
                UUID(proposal.character_id),
                selection.check.skill_id,
            )
            if inputs is None:
                raise QueueError(403, "invalid_character")
            with self.presence.guard(command.campaign_id) as presence:
                actor = str(command.actor_id)
                if queue.current != actor or command.actor_id not in presence.online_guest_ids:
                    raise QueueError(409, "not_your_turn")
                resolved = resolve_noncombat_check(
                    inputs.characteristic, inputs.skill, self.roller()
                )
                result: dict[str, object] = {
                    "dice": list(resolved.dice),
                    "characteristic": inputs.characteristic,
                    "skill": inputs.skill,
                    "modifier": resolved.modifier,
                    "difficulty": selection.check.difficulty,
                    "total": resolved.total,
                    "success": resolved.success,
                }
                public_outcome = self.adventures.apply_check(
                    command.campaign_id,
                    proposal.encounter_id,
                    proposal.object_id,
                    proposal.solution_id,
                    resolved.success,
                )
                self.proposals.save(
                    command.campaign_id,
                    collection.confirm(proposal.id, actor, actor),
                    collection.version,
                )
                self.queues.save(
                    command.campaign_id, encounter_id, queue.complete(actor), queue.version
                )
                self.checks.record(
                    command,
                    {
                        "result": result,
                        "rules": "noncombat-v1",
                        "actor_id": actor,
                        "character_id": proposal.character_id,
                        "skill_id": selection.check.skill_id,
                        "encounter_id": encounter_id,
                        "proposal_id": proposal.id,
                    },
                    result,
                )
                event_id = self.stager.stage(
                    command.campaign_id,
                    result,
                    self.clock(),
                    tuple(f.text for f in public_outcome.facts),
                )
                self.proposals.commit()
        except BaseException:
            self.proposals.rollback()
            raise
        try:
            self.notifier.notify(command.campaign_id, event_id)
        except Exception:
            logger.warning("Check notification failed after commit", exc_info=True)
        return result, False

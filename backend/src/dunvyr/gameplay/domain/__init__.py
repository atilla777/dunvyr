"""Pure gameplay domain."""

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class ProposedAction:
    id: str
    owner: str
    character_id: str
    encounter_id: str
    object_id: str
    solution_id: str
    fingerprint: str
    cancelled: bool = False


@dataclass(frozen=True)
class ProposalCollection:
    owner: str
    proposals: tuple[ProposedAction, ...] = ()
    version: int = 0

    @property
    def pending(self) -> tuple[ProposedAction, ...]:
        return tuple(proposal for proposal in self.proposals if not proposal.cancelled)

    def create(
        self,
        *,
        proposal_id: str,
        actor: str,
        character_id: str,
        encounter_id: str,
        object_id: str,
        solution_id: str,
        fingerprint: str,
    ) -> ProposalCollection:
        if (
            actor != self.owner
            or len(self.pending) >= 20
            or any(proposal.id == proposal_id for proposal in self.proposals)
        ):
            raise ValueError("invalid proposal creation")
        proposal = ProposedAction(
            proposal_id, actor, character_id, encounter_id, object_id, solution_id, fingerprint
        )
        return replace(self, proposals=(*self.proposals, proposal), version=self.version + 1)

    def _pending_for_turn(self, proposal_id: str, actor: str, current: str) -> ProposedAction:
        if actor != self.owner or current != actor:
            raise ValueError("not the owner's turn")
        proposal = next((p for p in self.pending if p.id == proposal_id), None)
        if proposal is None:
            raise ValueError("proposal unavailable")
        return proposal

    def _replace(self, proposal: ProposedAction) -> ProposalCollection:
        return replace(
            self,
            proposals=tuple(proposal if p.id == proposal.id else p for p in self.proposals),
            version=self.version + 1,
        )

    def edit(
        self,
        proposal_id: str,
        actor: str,
        current: str,
        character_id: str,
        encounter_id: str,
        object_id: str,
        solution_id: str,
        fingerprint: str,
    ) -> ProposalCollection:
        proposal = self._pending_for_turn(proposal_id, actor, current)
        if proposal.character_id != character_id:
            raise ValueError("character does not match")
        return self._replace(
            replace(
                proposal,
                encounter_id=encounter_id,
                object_id=object_id,
                solution_id=solution_id,
                fingerprint=fingerprint,
            )
        )

    def cancel(self, proposal_id: str, actor: str, current: str) -> ProposalCollection:
        return self._replace(
            replace(self._pending_for_turn(proposal_id, actor, current), cancelled=True)
        )


@dataclass(frozen=True)
class Queue:
    base_order: tuple[tuple[str, str], ...]
    round_order: tuple[str, ...]
    round_number: int = 1
    cursor: int = 0
    skipped: tuple[str, ...] = ()
    version: int = 1

    @property
    def current(self) -> str | None:
        return self.round_order[self.cursor] if self.cursor < len(self.round_order) else None

    def swap(self, actor: str, target: str, online: set[str]) -> Queue:
        if (
            actor != self.current
            or actor not in online
            or target not in online
            or target not in self.round_order[self.cursor + 1 :]
        ):
            raise ValueError("swap requires the online current player and a later online player")
        order = list(self.round_order)
        target_index = order.index(target, self.cursor + 1)
        order[self.cursor], order[target_index] = order[target_index], order[self.cursor]
        return replace(self, round_order=tuple(order), version=self.version + 1)

    def normalize(self, online: set[str]) -> Queue:
        order, cursor, skipped, round_number = (
            self.round_order,
            self.cursor,
            self.skipped,
            self.round_number,
        )
        while cursor < len(order) and order[cursor] not in online:
            skipped += (order[cursor],)
            cursor += 1
        if cursor == len(order) and any(guest in online for guest, _ in self.base_order):
            order = tuple(guest for guest, _ in self.base_order)
            cursor, skipped, round_number = 0, (), round_number + 1
            while cursor < len(order) and order[cursor] not in online:
                skipped += (order[cursor],)
                cursor += 1
        if (order, cursor, skipped, round_number) == (
            self.round_order,
            self.cursor,
            self.skipped,
            self.round_number,
        ):
            return self
        return replace(
            self,
            round_order=order,
            cursor=cursor,
            skipped=skipped,
            round_number=round_number,
            version=self.version + 1,
        )


def start_queue(participants: tuple[tuple[str, str], ...]) -> Queue:
    if (
        not participants
        or any(not guest.strip() or not character.strip() for guest, character in participants)
        or len({guest for guest, _ in participants}) != len(participants)
        or len({character for _, character in participants}) != len(participants)
    ):
        raise ValueError("participants must have distinct, nonempty identities")
    return Queue(base_order=participants, round_order=tuple(p[0] for p in participants))

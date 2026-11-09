"""Pure gameplay domain."""

from dataclasses import dataclass, replace


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

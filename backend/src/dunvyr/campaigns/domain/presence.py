"""Pure in-memory connection presence model."""

from uuid import UUID


class Presence:
    def __init__(self, lease: float = 30.0, grace: float = 5.0) -> None:
        self.connections: dict[UUID, tuple[UUID, UUID]] = {}
        self.deadlines: dict[UUID, float] = {}
        self.grace: dict[tuple[UUID, UUID], float] = {}
        self.lease = lease
        self.grace_period = grace

    def connect(self, campaign: UUID, guest: UUID, connection: UUID, now: float) -> None:
        self.connections[connection] = (campaign, guest)
        self.deadlines[connection] = now + self.lease
        self.grace.pop((campaign, guest), None)

    def online(self, campaign: UUID, now: float) -> tuple[UUID, ...]:
        active = {g for c, g in self.connections.values() if c == campaign}
        active.update(g for (c, g), until in self.grace.items() if c == campaign and now < until)
        return tuple(sorted(active))

    def disconnect(self, connection: UUID, now: float) -> None:
        deadline = self.deadlines.pop(connection, None)
        pair = self.connections.pop(connection, None)
        if pair is not None and pair not in self.connections.values():
            self.grace[pair] = (
                min(now, deadline if deadline is not None else now) + self.grace_period
            )

    def sweep(self, now: float) -> None:
        for connection, deadline in sorted(self.deadlines.items(), key=lambda item: item[1]):
            if deadline <= now:
                self.disconnect(connection, deadline)
        self.grace = {pair: deadline for pair, deadline in self.grace.items() if deadline > now}

    def renew(self, connection: UUID, now: float) -> bool:
        deadline = self.deadlines.get(connection)
        if deadline is None or now >= deadline:
            return False
        self.deadlines[connection] = now + self.lease
        return True

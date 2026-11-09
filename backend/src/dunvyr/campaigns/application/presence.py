"""Synchronized process-local presence, independent of any database transaction."""

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Lock
from time import monotonic
from uuid import UUID, uuid4

from dunvyr.campaigns.domain.presence import Presence
from dunvyr.campaigns.public import PresencePublisher, PresenceState

logger = logging.getLogger(__name__)


class PresenceRuntime:
    def __init__(
        self,
        publisher: PresencePublisher,
        *,
        clock: Callable[[], float] = monotonic,
        lease: float = 30.0,
        grace: float = 5.0,
    ) -> None:
        self._publisher = publisher
        self._clock = clock
        self._model = Presence(lease=lease, grace=grace)
        self._epoch = uuid4()
        self._lock = Lock()
        self._states: dict[UUID, PresenceState] = {}

    def _collect(self, now: float) -> list[tuple[UUID, PresenceState]]:
        self._model.sweep(now)
        changes = []
        for campaign_id, state in self._states.items():
            online = self._model.online(campaign_id, now)
            if online != state.online_guest_ids:
                updated = PresenceState(self._epoch, state.revision + 1, online)
                self._states[campaign_id] = updated
                changes.append((campaign_id, updated))
        return changes

    def _publish(self, changes: list[tuple[UUID, PresenceState]]) -> None:
        for campaign_id, state in changes:
            try:
                self._publisher.publish(campaign_id, state)
            except Exception:
                logger.warning("Presence notification failed", exc_info=True)

    def connect(self, campaign_id: UUID, guest_id: UUID, connection_id: UUID) -> None:
        with self._lock:
            now = self._clock()
            changes = self._collect(now)
            self._states.setdefault(campaign_id, PresenceState(self._epoch, 0, ()))
            self._model.connect(campaign_id, guest_id, connection_id, now)
            changes.extend(self._collect(now))
        self._publish(changes)

    def disconnect(self, connection_id: UUID) -> None:
        with self._lock:
            now = self._clock()
            changes = self._collect(now)
            self._model.disconnect(connection_id, now)
            changes.extend(self._collect(now))
        self._publish(changes)

    def renew(self, connection_id: UUID) -> bool:
        with self._lock:
            now = self._clock()
            changes = self._collect(now)
            renewed = self._model.renew(connection_id, now)
        self._publish(changes)
        return renewed

    def sweep(self) -> None:
        with self._lock:
            changes = self._collect(self._clock())
        self._publish(changes)

    def read(self, campaign_id: UUID) -> PresenceState:
        with self._lock:
            changes = self._collect(self._clock())
            state = self._states.setdefault(campaign_id, PresenceState(self._epoch, 0, ()))
        self._publish(changes)
        return state

    @contextmanager
    def guard(self, campaign_id: UUID) -> Iterator[PresenceState]:
        changes: list[tuple[UUID, PresenceState]] = []
        try:
            with self._lock:
                changes = self._collect(self._clock())
                yield self._states.setdefault(campaign_id, PresenceState(self._epoch, 0, ()))
        finally:
            self._publish(changes)

"""In-process realtime fan-out hub (no Redis/queues in the MVP)."""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from uuid import UUID, uuid4

from dunvyr.campaigns.public import PresenceState


@dataclass(slots=True)
class _Subscriber:
    loop: asyncio.AbstractEventLoop
    queue: asyncio.Queue[dict[str, object]]
    guest_id: UUID | None


def _enqueue(queue: asyncio.Queue[dict[str, object]], payload: dict[str, object]) -> None:
    queue.put_nowait(payload)


class RealtimeHub:
    """Thread-safe registry of per-campaign WebSocket subscriber queues."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[UUID, dict[int, _Subscriber]] = {}
        self._next_token = 0

    def subscribe(
        self, campaign_id: UUID, guest_id: UUID | None = None
    ) -> tuple[int, asyncio.Queue[dict[str, object]]]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
        with self._lock:
            token = self._next_token
            self._next_token += 1
            self._subscribers.setdefault(campaign_id, {})[token] = _Subscriber(
                loop=loop, queue=queue, guest_id=guest_id
            )
        return token, queue

    def unsubscribe(self, campaign_id: UUID, token: int) -> None:
        with self._lock:
            subscribers = self._subscribers.get(campaign_id)
            if subscribers is None:
                return
            subscribers.pop(token, None)
            if not subscribers:
                self._subscribers.pop(campaign_id, None)

    def broadcast(self, campaign_id: UUID, payload: dict[str, object]) -> None:
        """Enqueue one payload for every currently connected campaign client."""
        with self._lock:
            subscribers = tuple(self._subscribers.get(campaign_id, {}).values())
        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(_enqueue, subscriber.queue, payload)
            except RuntimeError:
                # The subscriber loop is already closed; its handler will clean up.
                continue

    def subscriber_count(self, campaign_id: UUID) -> int:
        with self._lock:
            return len(self._subscribers.get(campaign_id, {}))

    def proposals_changed(self, campaign_id: UUID, actor_id: UUID) -> None:
        """Enqueue only a content-free invalidation for the owner's connections."""
        with self._lock:
            subscribers = tuple(
                subscriber
                for subscriber in self._subscribers.get(campaign_id, {}).values()
                if subscriber.guest_id == actor_id
            )
        payload: dict[str, object] = {"type": "proposals_changed", "campaign_id": str(campaign_id)}
        for subscriber in subscribers:
            try:
                subscriber.loop.call_soon_threadsafe(_enqueue, subscriber.queue, payload)
            except RuntimeError:
                continue

    def publish(self, campaign_id: UUID, state: PresenceState) -> None:
        self.broadcast(
            campaign_id,
            {
                "type": "presence_state",
                "event_id": str(uuid4()),
                "campaign_id": str(campaign_id),
                "presence_state": {
                    "epoch": str(state.epoch),
                    "revision": state.revision,
                    "online_guest_ids": [str(guest) for guest in state.online_guest_ids],
                },
            },
        )


__all__ = ["RealtimeHub"]

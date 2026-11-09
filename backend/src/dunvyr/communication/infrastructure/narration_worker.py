"""Two tracked polling slots; network runs only between closed DB sessions."""

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from dunvyr.communication.infrastructure.narrations import NarrationRepository
from dunvyr.narration.public import NarrationModel

logger = logging.getLogger(__name__)


async def _database[T](operation: Callable[[], T]) -> T:
    # Cancelling to_thread only cancels its waiter, not the DB operation. Keep
    # that operation tracked until its short transaction/session has closed.
    task = asyncio.create_task(asyncio.to_thread(operation))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        await task
        raise


class NarrationWorker:
    def __init__(
        self,
        sessions: sessionmaker[Session],
        model: NarrationModel,
        notify: Callable[[UUID, UUID], None],
        clock: Callable[[], datetime],
    ) -> None:
        self.sessions, self.model, self.notify, self.clock = sessions, model, notify, clock

    def _notify(self, campaign_id: UUID, event_id: UUID) -> None:
        try:
            self.notify(campaign_id, event_id)
        except Exception:
            logger.warning("Narration delivery failed; durable history remains available")

    def _claim(self) -> dict[str, Any] | None:
        with self.sessions() as session:
            repo = NarrationRepository(session)
            recovered = repo.recover(self.clock())
            claim = repo.claim(self.clock())
            session.commit()
        for campaign_id, event_id in recovered:
            self._notify(campaign_id, event_id)
        if claim is not None:
            self._notify(UUID(claim["campaign_id"]), claim["event_id"])
        return claim

    def _complete(self, claim: dict[str, Any], text: str | None, error: str | None) -> None:
        with self.sessions() as session:
            event_id = NarrationRepository(session).complete(claim, text, error, self.clock())
            session.commit()
        if event_id is not None:
            self._notify(UUID(claim["campaign_id"]), event_id)

    async def process_once(self) -> bool:
        claim = await _database(self._claim)
        if claim is None:
            return False
        text, error = None, None
        try:
            context = json.loads(claim["context"])
            async with asyncio.timeout(20):
                text = await self.model.generate(context["success"], tuple(context["facts"]))
        except Exception:
            error = "retryable_provider_error"
        await _database(lambda: self._complete(claim, text, error))
        return True

    async def run(self, stop: asyncio.Event, interval: float = 0.25) -> None:
        async def slot() -> None:
            while not stop.is_set():
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), interval)
                if stop.is_set():
                    return
                try:
                    await self.process_once()
                except Exception:
                    logger.warning("Narration polling failed; will recover on next poll")

        tasks = [asyncio.create_task(slot()) for _ in range(2)]
        try:
            await stop.wait()
        finally:
            # A cancelled network attempt remains recoverable from its lease.
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

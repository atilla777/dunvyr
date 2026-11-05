"""Ports the communication application layer depends on."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from dunvyr.communication.domain.events import ChatEvent, MemberJoinedEvent, MessageEvent

Clock = Callable[[], datetime]
IdFactory = Callable[[], UUID]


class ChatEventRepository(Protocol):
    def find_message_by_client_id(
        self,
        campaign_id: UUID,
        client_message_id: UUID,
    ) -> MessageEvent | None: ...

    def find_member_joined(
        self,
        campaign_id: UUID,
        guest_id: UUID,
    ) -> MemberJoinedEvent | None: ...

    def next_sequence(self, campaign_id: UUID) -> int: ...

    def append(self, event: ChatEvent) -> None: ...

    def list_events(
        self,
        campaign_id: UUID,
        *,
        after_sequence: int | None,
        limit: int,
    ) -> list[ChatEvent]: ...

    def last_sequence(self, campaign_id: UUID) -> int: ...


class ChatUnitOfWork(Protocol):
    @property
    def events(self) -> ChatEventRepository: ...

    def commit(self) -> None: ...


__all__ = ["ChatEventRepository", "ChatUnitOfWork", "Clock", "IdFactory"]

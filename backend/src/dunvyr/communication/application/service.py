"""Communication application services: send chat messages and read history."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from dunvyr.campaigns.public import CampaignMembershipReader, CampaignMemberSnapshot
from dunvyr.communication.application.errors import (
    ClientMessageConflict,
    EventAppendConflict,
    NotAMember,
)
from dunvyr.communication.application.ports import ChatUnitOfWork, Clock, IdFactory
from dunvyr.communication.domain.events import (
    ChatEvent,
    ChatMember,
    MemberJoinedEvent,
    MessageEvent,
)
from dunvyr.communication.domain.message import Message, MessageAuthor

DEFAULT_HISTORY_LIMIT = 200
MAX_APPEND_ATTEMPTS = 3


@dataclass(frozen=True, slots=True)
class SendMessage:
    """Client command: the author identity is always the server session guest."""

    campaign_id: UUID
    author_id: UUID
    client_message_id: UUID
    content: str


@dataclass(frozen=True, slots=True)
class SendMessageResult:
    event: MessageEvent
    created: bool


@dataclass(frozen=True, slots=True)
class ChatHistory:
    events: tuple[ChatEvent, ...]
    last_sequence: int


@dataclass(frozen=True, slots=True)
class RecordMemberJoinedResult:
    event: MemberJoinedEvent
    created: bool


class ChatService:
    """Chat use cases: post a message and read one campaign event stream."""

    def __init__(
        self,
        *,
        unit_of_work: ChatUnitOfWork,
        membership_reader: CampaignMembershipReader,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._membership_reader = membership_reader
        self._clock = clock
        self._id_factory = id_factory

    def _require_member(self, campaign_id: UUID, guest_id: UUID) -> CampaignMemberSnapshot:
        member = self._membership_reader.find_member(campaign_id, guest_id)
        if member is None:
            raise NotAMember
        return member

    def send_message(self, command: SendMessage) -> SendMessageResult:
        """Persist one message and its stream event; replay repeats are idempotent."""
        member = self._require_member(command.campaign_id, command.author_id)

        existing = self._unit_of_work.events.find_message_by_client_id(
            command.campaign_id,
            command.client_message_id,
        )
        if existing is not None:
            return self._replay(existing, command.author_id)

        now = self._clock()
        message = Message.create(
            id=self._id_factory(),
            campaign_id=command.campaign_id,
            author=MessageAuthor(
                campaign_id=command.campaign_id,
                guest_id=member.guest_id,
                nickname=member.nickname,
            ),
            client_message_id=command.client_message_id,
            content=command.content,
            created_at=now,
        )

        for _attempt in range(MAX_APPEND_ATTEMPTS):
            event = MessageEvent.create(
                event_id=self._id_factory(),
                sequence=self._unit_of_work.events.next_sequence(command.campaign_id),
                occurred_at=now,
                message=message,
            )
            try:
                self._unit_of_work.events.append(event)
            except EventAppendConflict:
                existing = self._unit_of_work.events.find_message_by_client_id(
                    command.campaign_id,
                    command.client_message_id,
                )
                if existing is not None:
                    return self._replay(existing, command.author_id)
                continue
            self._unit_of_work.commit()
            return SendMessageResult(event=event, created=True)

        raise EventAppendConflict("message sequence could not be assigned")

    @staticmethod
    def _replay(existing: MessageEvent, author_id: UUID) -> SendMessageResult:
        if existing.message.author_id != author_id:
            raise ClientMessageConflict
        return SendMessageResult(event=existing, created=False)

    def get_history(
        self,
        campaign_id: UUID,
        viewer_id: UUID,
        *,
        after_sequence: int | None = None,
        limit: int = DEFAULT_HISTORY_LIMIT,
    ) -> ChatHistory:
        """Return the member-only chronological stream, optionally after a cursor."""
        self._require_member(campaign_id, viewer_id)
        events = self._unit_of_work.events.list_events(
            campaign_id,
            after_sequence=after_sequence,
            limit=limit,
        )
        return ChatHistory(
            events=tuple(events),
            last_sequence=self._unit_of_work.events.last_sequence(campaign_id),
        )


class MemberEventService:
    """Persist campaign membership facts into the same communication stream."""

    def __init__(
        self,
        *,
        unit_of_work: ChatUnitOfWork,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._clock = clock
        self._id_factory = id_factory

    def record_member_joined(
        self,
        campaign_id: UUID,
        member: CampaignMemberSnapshot,
    ) -> RecordMemberJoinedResult:
        """Persist one membership fact; repeated deliveries replay the event."""
        existing = self._unit_of_work.events.find_member_joined(campaign_id, member.guest_id)
        if existing is not None:
            return RecordMemberJoinedResult(event=existing, created=False)

        now = self._clock()
        chat_member = ChatMember(
            guest_id=member.guest_id,
            nickname=member.nickname,
            role=member.role,
            joined_at=member.joined_at,
        )

        for _attempt in range(MAX_APPEND_ATTEMPTS):
            event = MemberJoinedEvent.create(
                event_id=self._id_factory(),
                campaign_id=campaign_id,
                sequence=self._unit_of_work.events.next_sequence(campaign_id),
                occurred_at=now,
                member=chat_member,
            )
            try:
                self._unit_of_work.events.append(event)
            except EventAppendConflict:
                existing = self._unit_of_work.events.find_member_joined(
                    campaign_id,
                    member.guest_id,
                )
                if existing is not None:
                    return RecordMemberJoinedResult(event=existing, created=False)
                continue
            self._unit_of_work.commit()
            return RecordMemberJoinedResult(event=event, created=True)

        raise EventAppendConflict("member event sequence could not be assigned")


__all__ = [
    "DEFAULT_HISTORY_LIMIT",
    "ChatHistory",
    "ChatService",
    "MemberEventService",
    "RecordMemberJoinedResult",
    "SendMessage",
    "SendMessageResult",
]

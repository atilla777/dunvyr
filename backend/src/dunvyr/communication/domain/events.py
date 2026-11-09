"""Immutable chat stream events shared by history and live delivery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from dunvyr.communication.domain.message import (
    InvalidMessage,
    Message,
    _require_aware,
    _validate_nickname,
)

MEMBER_ROLES = frozenset({"organizer", "player"})


class InvalidEvent(ValueError):
    """Raised when a chat stream event violates its invariants."""


@dataclass(frozen=True, slots=True)
class ChatMember:
    """A member snapshot carried by a membership event."""

    guest_id: UUID
    nickname: str
    role: str
    joined_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.guest_id, UUID):
            raise InvalidEvent("event member guest_id must be a UUID")
        try:
            _validate_nickname(self.nickname)
        except InvalidMessage as error:
            raise InvalidEvent(f"event member: {error}") from error
        if self.role not in MEMBER_ROLES:
            raise InvalidEvent("event member role must be organizer or player")
        try:
            _require_aware(self.joined_at, "joined_at")
        except InvalidMessage as error:
            raise InvalidEvent(f"event member: {error}") from error


def _validate_envelope(
    *,
    event_id: UUID,
    campaign_id: UUID,
    sequence: int,
    occurred_at: datetime,
) -> None:
    if not isinstance(event_id, UUID):
        raise InvalidEvent("event event_id must be a UUID")
    if not isinstance(campaign_id, UUID):
        raise InvalidEvent("event campaign_id must be a UUID")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
        raise InvalidEvent("event sequence must be a positive integer")
    try:
        _require_aware(occurred_at, "occurred_at")
    except InvalidMessage as error:
        raise InvalidEvent(str(error)) from error


@dataclass(frozen=True, slots=True)
class MessageEvent:
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    message: Message

    def __post_init__(self) -> None:
        _validate_envelope(
            event_id=self.event_id,
            campaign_id=self.campaign_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
        )
        if not isinstance(self.message, Message):
            raise InvalidEvent("message event must carry a Message")
        if self.message.campaign_id != self.campaign_id:
            raise InvalidEvent("message event campaign must match the message campaign")

    @classmethod
    def create(
        cls,
        *,
        event_id: UUID,
        sequence: int,
        occurred_at: datetime,
        message: Message,
    ) -> MessageEvent:
        return cls(
            event_id=event_id,
            campaign_id=message.campaign_id,
            sequence=sequence,
            occurred_at=occurred_at,
            message=message,
        )


@dataclass(frozen=True, slots=True)
class MemberJoinedEvent:
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    member: ChatMember

    def __post_init__(self) -> None:
        _validate_envelope(
            event_id=self.event_id,
            campaign_id=self.campaign_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
        )
        if not isinstance(self.member, ChatMember):
            raise InvalidEvent("member_joined event must carry a ChatMember")

    @classmethod
    def create(
        cls,
        *,
        event_id: UUID,
        campaign_id: UUID,
        sequence: int,
        occurred_at: datetime,
        member: ChatMember,
    ) -> MemberJoinedEvent:
        return cls(
            event_id=event_id,
            campaign_id=campaign_id,
            sequence=sequence,
            occurred_at=occurred_at,
            member=member,
        )


@dataclass(frozen=True, slots=True)
class GameSessionChangedEvent:
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    revision: int
    session_id: UUID
    status: str
    started_at: datetime
    ended_at: datetime | None

    def __post_init__(self) -> None:
        _validate_envelope(
            event_id=self.event_id,
            campaign_id=self.campaign_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
        )
        if self.revision < 1 or self.status not in {"running", "paused", "ended"}:
            raise InvalidEvent("Invalid session state")


@dataclass(frozen=True, slots=True)
class QueueChangedEvent:
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    version: int
    state_json: str

    def __post_init__(self) -> None:
        _validate_envelope(
            event_id=self.event_id,
            campaign_id=self.campaign_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
        )
        if type(self.version) is not int or self.version < 1:
            raise InvalidEvent("Invalid queue version")


@dataclass(frozen=True, slots=True)
class CheckResolvedEvent:
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    result_json: str

    def __post_init__(self) -> None:
        _validate_envelope(
            event_id=self.event_id,
            campaign_id=self.campaign_id,
            sequence=self.sequence,
            occurred_at=self.occurred_at,
        )


ChatEvent = (
    MessageEvent
    | MemberJoinedEvent
    | GameSessionChangedEvent
    | QueueChangedEvent
    | CheckResolvedEvent
)


__all__ = [
    "ChatEvent",
    "ChatMember",
    "InvalidEvent",
    "MemberJoinedEvent",
    "MessageEvent",
]

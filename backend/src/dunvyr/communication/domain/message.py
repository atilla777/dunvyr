"""Chat message entity and its invariants."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

MESSAGE_MAX_LENGTH = 2000
AUTHOR_NICKNAME_MAX_LENGTH = 32


class InvalidMessage(ValueError):
    """Raised when a chat message violates its invariants."""


def _require_aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime):
        raise InvalidMessage(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidMessage(f"{field} must be timezone-aware")


def _validate_nickname(nickname: str) -> None:
    if not isinstance(nickname, str):
        raise InvalidMessage("author nickname must be a string")
    if nickname != nickname.strip():
        raise InvalidMessage("author nickname must not have surrounding whitespace")
    if not 1 <= len(nickname) <= AUTHOR_NICKNAME_MAX_LENGTH:
        raise InvalidMessage("author nickname must be 1..32 characters")
    if any(
        unicodedata.category(character).startswith("C") and character not in "\n\t"
        for character in nickname
    ):
        raise InvalidMessage("author nickname must not contain control characters")


def _validate_content(content: str) -> str:
    if not isinstance(content, str):
        raise InvalidMessage("message content must be a string")
    stripped = content.strip()
    if not stripped:
        raise InvalidMessage("message content must not be blank")
    if len(stripped) > MESSAGE_MAX_LENGTH:
        raise InvalidMessage(f"message content must be {MESSAGE_MAX_LENGTH} characters or fewer")
    if any(
        unicodedata.category(character).startswith("C") and character not in "\n\t"
        for character in stripped
    ):
        raise InvalidMessage("message content must not contain control characters")
    return stripped


@dataclass(frozen=True, slots=True)
class MessageAuthor:
    """A verified campaign member allowed to post into its chat stream."""

    campaign_id: UUID
    guest_id: UUID
    nickname: str

    def __post_init__(self) -> None:
        if not isinstance(self.campaign_id, UUID):
            raise InvalidMessage("author campaign_id must be a UUID")
        if not isinstance(self.guest_id, UUID):
            raise InvalidMessage("author guest_id must be a UUID")
        _validate_nickname(self.nickname)


@dataclass(frozen=True, slots=True)
class Message:
    """An immutable saved chat message; the server owns every field."""

    id: UUID
    campaign_id: UUID
    author_id: UUID
    author_nickname: str
    client_message_id: UUID
    content: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise InvalidMessage("message id must be a UUID")
        if not isinstance(self.campaign_id, UUID):
            raise InvalidMessage("message campaign_id must be a UUID")
        if not isinstance(self.author_id, UUID):
            raise InvalidMessage("message author_id must be a UUID")
        _validate_nickname(self.author_nickname)
        if not isinstance(self.client_message_id, UUID):
            raise InvalidMessage("message client_message_id must be a UUID")
        object.__setattr__(self, "content", _validate_content(self.content))
        _require_aware(self.created_at, "created_at")

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        campaign_id: UUID,
        author: MessageAuthor,
        client_message_id: UUID,
        content: str,
        created_at: datetime,
    ) -> Message:
        """Create a message authored by a verified member of its campaign."""
        if not isinstance(author, MessageAuthor):
            raise InvalidMessage("message author must be a verified member")
        if author.campaign_id != campaign_id:
            raise InvalidMessage("message author must belong to the message campaign")
        return cls(
            id=id,
            campaign_id=campaign_id,
            author_id=author.guest_id,
            author_nickname=author.nickname,
            client_message_id=client_message_id,
            content=content,
            created_at=created_at,
        )


__all__ = [
    "AUTHOR_NICKNAME_MAX_LENGTH",
    "MESSAGE_MAX_LENGTH",
    "InvalidMessage",
    "Message",
    "MessageAuthor",
]

"""Communication application errors mapped to API/WebSocket error codes."""

from __future__ import annotations


class CommunicationError(Exception):
    """Base class for communication use-case failures."""


class NotAMember(CommunicationError):
    """The authenticated guest is not a member of the campaign."""


class ClientMessageConflict(CommunicationError):
    """A different author already used this client message identifier."""


class EventAppendConflict(CommunicationError):
    """A concurrent writer won the stream sequence or idempotency race."""


__all__ = [
    "ClientMessageConflict",
    "CommunicationError",
    "EventAppendConflict",
    "NotAMember",
]

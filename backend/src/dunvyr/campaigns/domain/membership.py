"""Campaign membership: who belongs to the group and in which role."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from dunvyr.campaigns.domain.time import require_aware

NICKNAME_MAX_LENGTH = 32


class InvalidMembership(ValueError):
    """Raised when a campaign membership violates its invariants."""


class MemberRole(StrEnum):
    ORGANIZER = "organizer"
    PLAYER = "player"


def _is_control(character: str) -> bool:
    return unicodedata.category(character).startswith("C")


def _validate_nickname(nickname: str) -> None:
    if not isinstance(nickname, str):
        raise InvalidMembership("Member nickname must be a string")
    if nickname != nickname.strip():
        raise InvalidMembership("Member nickname must not have surrounding whitespace")
    if not 1 <= len(nickname) <= NICKNAME_MAX_LENGTH:
        raise InvalidMembership(
            f"Member nickname must be {NICKNAME_MAX_LENGTH} characters or fewer and not empty"
        )
    if any(_is_control(character) for character in nickname):
        raise InvalidMembership("Member nickname must not contain control characters")
    if not any(not character.isspace() for character in nickname):
        raise InvalidMembership(
            "Member nickname must contain at least one non-whitespace character"
        )


@dataclass(frozen=True, slots=True)
class Membership:
    """Immutable projection of a guest inside one campaign.

    The nickname is a display snapshot captured when the guest joined, so
    campaigns never has to query the identity tables for a member list.
    """

    guest_id: UUID
    nickname: str
    role: MemberRole
    joined_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.guest_id, UUID):
            raise InvalidMembership("Member guest_id must be a UUID")
        _validate_nickname(self.nickname)
        if not isinstance(self.role, MemberRole):
            raise InvalidMembership("Member role must be a MemberRole")
        try:
            require_aware(self.joined_at, "joined_at")
        except ValueError as error:
            raise InvalidMembership(str(error)) from error

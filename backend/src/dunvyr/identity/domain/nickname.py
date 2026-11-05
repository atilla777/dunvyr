"""Nickname value object enforcing the guest display-name rules."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

NICKNAME_MAX_LENGTH = 32


class InvalidNickname(ValueError):
    """Raised when a nickname violates the identity rules."""


def _is_control(character: str) -> bool:
    # Cc are control characters; Cf are invisible formatting characters such as
    # zero-width spaces, which must not be able to fake an empty display name.
    return unicodedata.category(character).startswith("C")


@dataclass(frozen=True, slots=True)
class Nickname:
    """A canonical, displayable nickname.

    Invariants: no surrounding whitespace, 1-32 Unicode code points, no control
    characters and at least one non-whitespace character.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidNickname("Nickname must be a string")
        if self.value != self.value.strip():
            raise InvalidNickname("Nickname must not have surrounding whitespace")
        if not 1 <= len(self.value) <= NICKNAME_MAX_LENGTH:
            raise InvalidNickname(
                f"Nickname must be {NICKNAME_MAX_LENGTH} characters or fewer and not empty"
            )
        if any(_is_control(character) for character in self.value):
            raise InvalidNickname("Nickname must not contain control characters")
        if not any(not character.isspace() for character in self.value):
            raise InvalidNickname("Nickname must contain at least one non-whitespace character")

    @classmethod
    def parse(cls, raw: object) -> Nickname:
        """Trim surrounding whitespace and validate the result."""
        if not isinstance(raw, str):
            raise InvalidNickname("Nickname must be a string")
        return cls(value=raw.strip())

    def __str__(self) -> str:
        return self.value

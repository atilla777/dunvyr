"""Value object for a campaign display name."""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

CAMPAIGN_NAME_MAX_LENGTH = 60


class InvalidCampaignName(ValueError):
    """Raised when a campaign name violates the naming rules."""


def _is_control(character: str) -> bool:
    # Cc are control characters; Cf are invisible formatting characters.
    return unicodedata.category(character).startswith("C")


@dataclass(frozen=True, slots=True)
class CampaignName:
    """A canonical campaign display name.

    Invariants: no surrounding whitespace, 1-60 Unicode code points, no control
    characters and at least one non-whitespace character.
    """

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidCampaignName("Campaign name must be a string")
        if self.value != self.value.strip():
            raise InvalidCampaignName("Campaign name must not have surrounding whitespace")
        if not 1 <= len(self.value) <= CAMPAIGN_NAME_MAX_LENGTH:
            raise InvalidCampaignName(
                f"Campaign name must be {CAMPAIGN_NAME_MAX_LENGTH} characters or fewer "
                "and not empty"
            )
        if any(_is_control(character) for character in self.value):
            raise InvalidCampaignName("Campaign name must not contain control characters")
        if not any(not character.isspace() for character in self.value):
            raise InvalidCampaignName(
                "Campaign name must contain at least one non-whitespace character"
            )

    @classmethod
    def parse(cls, raw: object) -> CampaignName:
        if not isinstance(raw, str):
            raise InvalidCampaignName("Campaign name must be a string")
        return cls(value=raw.strip())

    def __str__(self) -> str:
        return self.value

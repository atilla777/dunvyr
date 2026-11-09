"""Minimal character eligibility, with saved-card validation owned by characters."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class EligibleCharacter:
    id: UUID
    guest_id: UUID


class CharacterEligibilityReader(Protocol):
    def eligible(self, campaign_id: UUID, guest_id: UUID) -> EligibleCharacter | None: ...


@dataclass(frozen=True, slots=True)
class CharacterCheckInput:
    characteristic: int
    skill: int


class CharacterCheckInputReader(Protocol):
    def check_input(
        self, campaign_id: UUID, guest_id: UUID, character_id: UUID, skill_id: str
    ) -> CharacterCheckInput | None: ...

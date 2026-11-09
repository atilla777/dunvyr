"""Validate the persisted card against its pinned creation policy, never trust JSON."""

from dataclasses import asdict
from typing import cast
from uuid import UUID

from dunvyr.adventures.public import PinnedTemplatesReader
from dunvyr.characters.domain.character import CharacterInput, validate_allocation
from dunvyr.characters.infrastructure.repository import CharacterRepository
from dunvyr.characters.public import EligibleCharacter


class SqlCharacterEligibilityReader:
    def __init__(self, repository: CharacterRepository, templates: PinnedTemplatesReader) -> None:
        self.repository, self.templates = repository, templates

    def eligible(self, campaign_id: UUID, guest_id: UUID) -> EligibleCharacter | None:
        try:
            card = self.repository.get(campaign_id, guest_id)
        except ValueError:
            return None
        templates = self.templates.templates(campaign_id)
        if (
            card is None
            or templates is None
            or templates.creation_rules_id != "archetype-budget-v1"
        ):
            return None
        try:
            if card["campaign_id"] != str(campaign_id) or card["guest_id"] != str(guest_id):
                return None
            values = CharacterInput.normalize(
                cast(str, card["name"]),
                cast(str, card["appearance"]),
                cast(str, card["archetype_id"]),
            )
            archetype = next(a for a in templates.archetypes if a.id == values.archetype_id)
            skills = cast(list[dict[str, object]], card["skills"])
            if len({s["id"] for s in skills}) != len(skills):
                return None
            validate_allocation(
                asdict(archetype.characteristics),
                {s.skill_id: s.value for s in archetype.skills},
                {s.id for s in templates.skills},
                cast(dict[str, int], card["characteristics"]),
                {cast(str, s["id"]): cast(int, s["value"]) for s in skills},
            )
            return EligibleCharacter(UUID(cast(str, card["id"])), guest_id)
        except KeyError, ValueError, TypeError, AttributeError, StopIteration:
            return None

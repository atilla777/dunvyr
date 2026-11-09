"""Minimal immutable templates for character creation, not scenario data."""

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class SkillTemplate:
    id: str
    name: str
    characteristic: str


@dataclass(frozen=True, slots=True)
class Characteristics:
    strength: int
    agility: int
    intellect: int
    presence: int


@dataclass(frozen=True, slots=True)
class SkillRating:
    skill_id: str
    value: int


@dataclass(frozen=True, slots=True)
class ArchetypeTemplate:
    id: str
    name: str
    characteristics: Characteristics
    skills: tuple[SkillRating, ...]


@dataclass(frozen=True, slots=True)
class PinnedTemplates:
    skills: tuple[SkillTemplate, ...]
    archetypes: tuple[ArchetypeTemplate, ...]
    creation_rules_id: str = "archetype-budget-v1"


class PinnedTemplatesReader(Protocol):
    def templates(self, campaign_id: UUID) -> PinnedTemplates | None: ...


@dataclass(frozen=True, slots=True)
class EncounterCheck:
    skill_id: str
    skill_name: str
    characteristic: str
    difficulty: int


@dataclass(frozen=True, slots=True)
class AvailableSolution:
    id: str
    name: str
    description: str
    check: EncounterCheck


@dataclass(frozen=True, slots=True)
class AvailableEncounter:
    id: str
    object_id: str
    name: str
    description: str
    solutions: tuple[AvailableSolution, ...]


@dataclass(frozen=True, slots=True)
class AvailableEncounterCatalog:
    fingerprint: str
    current_location_id: str
    encounters: tuple[AvailableEncounter, ...]


class AvailableEncounterCatalogReader(Protocol):
    def available_encounters(self, campaign_id: UUID) -> AvailableEncounterCatalog | None: ...


class AdventureCheckParticipant(Protocol):
    def apply_check(
        self, campaign_id: UUID, encounter_id: str, object_id: str, solution_id: str, success: bool
    ) -> None: ...

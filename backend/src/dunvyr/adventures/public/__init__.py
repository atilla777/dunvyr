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


class PinnedTemplatesReader(Protocol):
    def templates(self, campaign_id: UUID) -> PinnedTemplates | None: ...

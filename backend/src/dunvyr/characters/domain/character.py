"""Character creation values and normalization."""

from dataclasses import dataclass
from unicodedata import category


@dataclass(frozen=True, slots=True)
class CreationRules:
    id: str = "archetype-budget-v1"
    minimum: int = 0
    maximum: int = 10
    relative_limit: int = 1
    characteristic_cost: int = 2
    skill_cost: int = 1


CREATION_RULES = CreationRules()


def allocation_cost(characteristics: dict[str, int], skills: dict[str, int]) -> int:
    return CREATION_RULES.characteristic_cost * sum(
        characteristics.values()
    ) + CREATION_RULES.skill_cost * sum(skills.values())


def validate_allocation(
    baseline: dict[str, int],
    baseline_skills: dict[str, int],
    allowed_skills: set[str],
    characteristics: dict[str, int],
    skills: dict[str, int],
) -> int:
    """Apply the archetype's starting point budget."""
    keys = {"strength", "agility", "intellect", "presence"}
    if set(characteristics) != keys or not set(skills) <= allowed_skills:
        raise ValueError("invalid_character")
    for key, value in characteristics.items():
        if (
            type(value) is not int
            or not CREATION_RULES.minimum <= value <= CREATION_RULES.maximum
            or abs(value - baseline[key]) > CREATION_RULES.relative_limit
        ):
            raise ValueError("invalid_character")
    for key in allowed_skills:
        value = skills.get(key, 0)
        if (
            type(value) is not int
            or not CREATION_RULES.minimum <= value <= CREATION_RULES.maximum
            or abs(value - baseline_skills.get(key, 0)) > CREATION_RULES.relative_limit
        ):
            raise ValueError("invalid_character")
    budget = allocation_cost(baseline, baseline_skills)
    spent = allocation_cost(characteristics, skills)
    if spent > budget:
        raise ValueError("invalid_character")
    return spent


@dataclass(frozen=True, slots=True)
class CharacterInput:
    name: str
    appearance: str
    archetype_id: str

    @classmethod
    def normalize(cls, name: str, appearance: str, archetype_id: str) -> CharacterInput:
        name, appearance = name.strip(), appearance.strip()
        if not 1 <= len(name) <= 60 or not 1 <= len(appearance) <= 2000:
            raise ValueError("invalid_character")
        if any(category(c).startswith("C") for c in name + appearance):
            raise ValueError("invalid_character")
        return cls(name, appearance, archetype_id)

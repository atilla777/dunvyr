"""Character creation values and normalization."""

from dataclasses import dataclass
from unicodedata import category


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

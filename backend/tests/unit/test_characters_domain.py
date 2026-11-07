"""Validation of character creation values."""

import pytest

from dunvyr.characters.domain.character import CharacterInput


@pytest.mark.unit
def test_character_input_normalizes_edges() -> None:
    values = CharacterInput.normalize(" Ada ", " Blue coat ", "engineer")
    assert (values.name, values.appearance, values.archetype_id) == ("Ada", "Blue coat", "engineer")


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "appearance"),
    [
        ("", "coat"),
        ("x" * 61, "coat"),
        ("Ada", ""),
        ("Ada", "x" * 2001),
        ("Ada\x00", "coat"),
        ("Ada", "a\nb"),
    ],
)
def test_character_input_rejects_invalid_text(name: str, appearance: str) -> None:
    with pytest.raises(ValueError):
        CharacterInput.normalize(name, appearance, "engineer")

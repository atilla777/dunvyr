"""Validation of character creation values."""

import pytest

from dunvyr.characters.domain import character
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


@pytest.mark.unit
def test_allocation_accepts_exact_budget_and_rejects_overspending() -> None:
    validate = getattr(character, "validate_allocation", None)
    assert callable(validate), "domain must enforce the archetype budget"
    baseline = {"strength": 2, "agility": 2, "intellect": 3, "presence": 2}
    skills = {"repair": 3, "persuade": 2}
    assert validate(baseline, skills, {"repair", "persuade"}, baseline, skills) == 23
    with pytest.raises(ValueError, match="invalid_character"):
        validate(baseline, skills, {"repair", "persuade"}, baseline, {"repair": 4, "persuade": 2})


@pytest.mark.unit
@pytest.mark.parametrize("bad", [-1, 11, True, 2.0, "2"])
def test_allocation_rejects_non_integer_or_out_of_range_values(bad: object) -> None:
    baseline = {"strength": 2, "agility": 2, "intellect": 3, "presence": 2}
    values = dict(baseline)
    values["strength"] = bad  # type: ignore[assignment]
    with pytest.raises(ValueError, match="invalid_character"):
        character.validate_allocation(baseline, {}, {"repair"}, values, {})


@pytest.mark.unit
@pytest.mark.parametrize(
    ("values", "skills"),
    [
        ({"strength": 2, "agility": 2, "intellect": 3}, {}),
        ({"strength": 2, "agility": 2, "intellect": 3, "presence": 2, "other": 0}, {}),
        ({"strength": 0, "agility": 2, "intellect": 3, "presence": 2}, {}),
        ({"strength": 2, "agility": 2, "intellect": 3, "presence": 2}, {"unknown": 0}),
        ({"strength": 2, "agility": 2, "intellect": 3, "presence": 2}, {"repair": -1}),
        ({"strength": 2, "agility": 2, "intellect": 3, "presence": 2}, {"repair": True}),
        ({"strength": 2, "agility": 2, "intellect": 3, "presence": 2}, {"repair": 2}),
    ],
)
def test_allocation_rejects_invalid_shape_and_relative_values(
    values: dict[str, int], skills: dict[str, int]
) -> None:
    baseline = {"strength": 2, "agility": 2, "intellect": 3, "presence": 2}
    with pytest.raises(ValueError, match="invalid_character"):
        character.validate_allocation(baseline, {}, {"repair"}, values, skills)


@pytest.mark.unit
def test_sparse_skills_are_zero_and_boundaries_are_clipped() -> None:
    baseline = {"strength": 0, "agility": 10, "intellect": 0, "presence": 10}
    assert character.validate_allocation(baseline, {"repair": 1}, {"repair"}, baseline, {}) == 40
    with pytest.raises(ValueError, match="invalid_character"):
        character.validate_allocation(baseline, {"repair": 2}, {"repair"}, baseline, {})


@pytest.mark.unit
def test_absolute_extremes_and_exact_relative_boundaries() -> None:
    baseline = {"strength": 0, "agility": 10, "intellect": 2, "presence": 2}
    skills = {"repair": 10, "hacking": 0}
    values = {"strength": 1, "agility": 9, "intellect": 1, "presence": 3}
    assert character.validate_allocation(baseline, skills, set(skills), values, skills) == 38
    assert character.validate_allocation(baseline, skills, set(skills), baseline, skills) == 38
    for skill, value in (("repair", 11), ("hacking", -1), ("hacking", 2)):
        with pytest.raises(ValueError, match="invalid_character"):
            character.validate_allocation(
                baseline, skills, set(skills), values, {**skills, skill: value}
            )


@pytest.mark.unit
@pytest.mark.parametrize("bad", [True, 1.0, "1"])
def test_skill_requires_strict_integer_even_with_budget_available(bad: object) -> None:
    baseline = {"strength": 2, "agility": 2, "intellect": 3, "presence": 2}
    values = {**baseline, "strength": 1}
    with pytest.raises(ValueError, match="invalid_character"):
        character.validate_allocation(baseline, {}, {"repair"}, values, {"repair": bad})  # type: ignore[dict-item]

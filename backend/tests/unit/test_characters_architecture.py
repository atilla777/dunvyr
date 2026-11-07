"""Guard character-owned code against direct foreign-context table access.

This source-level check complements import contracts; it detects literal table
names, not identifiers assembled dynamically at runtime.
"""

import re
from pathlib import Path

import pytest

CHARACTERS = Path(__file__).resolve().parents[2] / "src" / "dunvyr" / "characters"
FOREIGN_TABLE = re.compile(
    r"\b(?:identity|campaigns|adventures|communication|gameplay|narration)_[a-z0-9_]+\b",
    re.IGNORECASE,
)


def foreign_tables(source: str) -> set[str]:
    return {match.group().lower() for match in FOREIGN_TABLE.finditer(source)}


@pytest.mark.unit
def test_character_code_does_not_access_foreign_tables() -> None:
    sources = sorted(CHARACTERS.rglob("*.py"))
    assert list((CHARACTERS / "infrastructure").rglob("*.py"))
    violations = {
        str(path.relative_to(CHARACTERS)): found
        for path in sources
        if (found := foreign_tables(path.read_text(encoding="utf-8")))
    }
    assert violations == {}


@pytest.mark.unit
@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ('query = "SELECT * FROM campaigns_members"', "campaigns_members"),
        ('query = "UPDATE identity_guests SET nickname = :name"', "identity_guests"),
        ('query = "INSERT INTO adventures_snapshots VALUES (:id)"', "adventures_snapshots"),
        ('query = "DELETE FROM communication_events"', "communication_events"),
        ('query = "update gameplay_future_table set value = 1"', "gameplay_future_table"),
        ('query = "SELECT * FROM narration_future_table"', "narration_future_table"),
    ],
)
def test_ownership_guard_detects_foreign_reads_and_writes(source: str, expected: str) -> None:
    assert foreign_tables(source) == {expected}


@pytest.mark.unit
def test_ownership_guard_allows_character_table() -> None:
    assert not foreign_tables('query = "INSERT INTO characters_characters VALUES (:id)"')

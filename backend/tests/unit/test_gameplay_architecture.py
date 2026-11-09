"""Literal foreign-table guard complements public-only import contracts."""

import re
from pathlib import Path

import pytest

GAMEPLAY = Path(__file__).resolve().parents[2] / "src" / "dunvyr" / "gameplay"
FOREIGN = re.compile(
    r"\b(?:campaigns|characters|adventures|identity|communication|narration)_[a-z0-9_]+\b",
    re.IGNORECASE,
)


@pytest.mark.unit
def test_gameplay_never_reads_or_writes_foreign_tables() -> None:
    violations = {
        str(path): FOREIGN.findall(path.read_text())
        for path in GAMEPLAY.rglob("*.py")
        if FOREIGN.search(path.read_text())
    }
    assert violations == {}


@pytest.mark.unit
@pytest.mark.parametrize(
    "statement",
    [
        "SELECT * FROM characters_characters",
        "UPDATE campaigns_session_state SET revision=2",
        "INSERT INTO communication_events VALUES (1)",
        "DELETE FROM adventures_snapshots",
    ],
)
def test_foreign_guard_catches_reads_and_writes(statement: str) -> None:
    assert FOREIGN.search(statement)

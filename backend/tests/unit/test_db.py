"""Unit tests for the SQLAlchemy engine infrastructure."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from dunvyr.infrastructure.db import (
    create_db_engine,
    is_in_memory_sqlite_url,
)


@pytest.mark.unit
def test_foreign_keys_pragma_is_enabled_on_new_connections() -> None:
    engine: Engine = create_db_engine("sqlite+pysqlite:///:memory:")
    try:
        with engine.connect() as connection:
            foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar_one()
    finally:
        engine.dispose()

    assert foreign_keys == 1


@pytest.mark.unit
def test_in_memory_flag_recognises_sqlite_memory_urls() -> None:
    assert is_in_memory_sqlite_url("sqlite+pysqlite:///:memory:")
    assert is_in_memory_sqlite_url("sqlite://")
    assert not is_in_memory_sqlite_url("sqlite:///./dunvyr.db")


@pytest.mark.unit
def test_file_engine_uses_wal_journal_mode(tmp_path: Path) -> None:
    database_file = tmp_path / "wal-check.db"
    engine: Engine = create_db_engine(f"sqlite:///{database_file}")
    try:
        with engine.connect() as connection:
            journal_mode = connection.execute(text("PRAGMA journal_mode")).scalar_one()
    finally:
        engine.dispose()

    assert journal_mode.lower() == "wal"

"""Integration tests proving the Alembic pipeline creates a real schema."""

from __future__ import annotations

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


@pytest.mark.integration
def test_migrations_create_alembic_version_and_business_tables(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.connect() as connection:
        table_names = set(inspect(connection).get_table_names())

    assert {
        "alembic_version",
        "app_metadata",
        "identity_guests",
        "identity_sessions",
    } <= table_names


@pytest.mark.integration
def test_technical_table_accepts_and_returns_rows(migrated_engine: Engine) -> None:
    with migrated_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO app_metadata (key, value) VALUES ('schema_owner', 'dunvyr')")
        )
        row = connection.execute(
            text("SELECT value FROM app_metadata WHERE key = 'schema_owner'")
        ).one()

    assert row == ("dunvyr",)


@pytest.mark.integration
def test_migration_head_is_recorded(migrated_engine: Engine) -> None:
    with migrated_engine.connect() as connection:
        version = connection.execute(text("SELECT version_num FROM alembic_version")).scalar_one()

    assert version == "0002"


@pytest.mark.integration
def test_identity_tables_use_owned_prefix_and_unique_token_hash(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.connect() as connection:
        identity_tables = {
            name for name in inspect(connection).get_table_names() if name.startswith("identity_")
        }
        unique_constraints = inspect(connection).get_unique_constraints("identity_sessions")

    assert identity_tables == {"identity_guests", "identity_sessions"}
    assert any(constraint["column_names"] == ["token_hash"] for constraint in unique_constraints)

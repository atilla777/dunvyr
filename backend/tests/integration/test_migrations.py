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
        "campaigns_campaigns",
        "campaigns_members",
        "communication_events",
        "adventures_snapshots",
        "adventures_resources",
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

    assert version == "0009"


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


@pytest.mark.integration
def test_campaigns_tables_use_owned_prefix_and_database_uniqueness(
    migrated_engine: Engine,
) -> None:
    with migrated_engine.connect() as connection:
        campaigns_tables = {
            name for name in inspect(connection).get_table_names() if name.startswith("campaigns_")
        }
        campaign_unique = inspect(connection).get_unique_constraints("campaigns_campaigns")
        member_unique = inspect(connection).get_unique_constraints("campaigns_members")
        member_primary_key = inspect(connection).get_pk_constraint("campaigns_members")
        member_foreign_keys = inspect(connection).get_foreign_keys("campaigns_members")

    assert campaigns_tables == {
        "campaigns_campaigns",
        "campaigns_members",
        "campaigns_game_sessions",
        "campaigns_session_state",
        "campaigns_session_receipts",
    }
    assert any(
        constraint["column_names"] == ["invitation_token_hash"] for constraint in campaign_unique
    )
    assert any(
        constraint["column_names"] == ["organizer_id", "idempotency_key"]
        for constraint in campaign_unique
    )
    assert any(
        constraint["column_names"] == ["campaign_id", "nickname"] for constraint in member_unique
    )
    assert member_primary_key["constrained_columns"] == ["campaign_id", "guest_id"]
    assert any(
        foreign_key["constrained_columns"] == ["campaign_id"]
        and foreign_key["referred_table"] == "campaigns_campaigns"
        and foreign_key["referred_columns"] == ["id"]
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in member_foreign_keys
    )

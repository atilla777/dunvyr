"""Unit tests for campaigns SQLAlchemy table ownership and constraints."""

from __future__ import annotations

import pytest
from sqlalchemy import UniqueConstraint

from dunvyr.campaigns.infrastructure import tables


@pytest.mark.unit
def test_campaigns_metadata_contains_only_owned_tables() -> None:
    names = set(tables.metadata.tables)

    assert names == {
        "campaigns_campaigns",
        "campaigns_members",
        "campaigns_game_sessions",
        "campaigns_session_state",
        "campaigns_session_receipts",
    }
    assert all(name.startswith("campaigns_") for name in names)


@pytest.mark.unit
def test_campaigns_schema_stores_only_a_unique_invitation_hash() -> None:
    campaign_table = tables.campaigns

    assert campaign_table.c.invitation_token_hash.unique
    assert not campaign_table.c.invitation_token_hash.nullable
    assert "invitation_secret" not in campaign_table.c
    assert "idempotency_key" in campaign_table.c


@pytest.mark.unit
def test_campaigns_schema_prevents_duplicate_organizer_idempotency_keys() -> None:
    unique_constraints = [
        tuple(column.name for column in constraint.columns)
        for constraint in tables.campaigns.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert ("organizer_id", "idempotency_key") in unique_constraints


@pytest.mark.unit
def test_campaign_members_reference_the_owned_campaign_table() -> None:
    foreign_keys = list(tables.members.c.campaign_id.foreign_keys)

    assert [fk.target_fullname for fk in foreign_keys] == ["campaigns_campaigns.id"]
    assert tables.members.c.campaign_id.primary_key
    assert tables.members.c.guest_id.primary_key


@pytest.mark.unit
def test_campaigns_schema_makes_member_nicknames_unique_per_campaign() -> None:
    unique_constraints = [
        tuple(column.name for column in constraint.columns)
        for constraint in tables.members.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert ("campaign_id", "nickname") in unique_constraints

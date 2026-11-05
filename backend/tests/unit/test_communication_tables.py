"""Unit tests for communication SQLAlchemy table ownership and constraints."""

from __future__ import annotations

import pytest
from sqlalchemy import UniqueConstraint

from dunvyr.communication.infrastructure import tables


@pytest.mark.unit
def test_communication_metadata_contains_only_owned_tables() -> None:
    names = set(tables.metadata.tables)

    assert names == {"communication_events"}
    assert all(name.startswith("communication_") for name in names)


@pytest.mark.unit
def test_communication_events_reference_campaigns_without_foreign_keys() -> None:
    foreign_keys = list(tables.communication_events.c.campaign_id.foreign_keys)

    assert foreign_keys == []
    assert not tables.communication_events.c.campaign_id.nullable


@pytest.mark.unit
def test_communication_events_sequence_is_primary_key_per_campaign() -> None:
    primary_key_columns = tuple(
        column.name for column in tables.communication_events.primary_key.columns
    )

    assert primary_key_columns == ("campaign_id", "sequence")


@pytest.mark.unit
def test_communication_events_make_event_and_client_ids_unique() -> None:
    unique_constraints = [
        tuple(column.name for column in constraint.columns)
        for constraint in tables.communication_events.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert ("campaign_id", "client_message_id") in unique_constraints
    assert ("campaign_id", "member_guest_id") in unique_constraints
    assert tables.communication_events.c.event_id.unique

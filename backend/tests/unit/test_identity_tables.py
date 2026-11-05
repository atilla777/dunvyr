"""Architecture test: identity owns only its own ``identity_*`` tables."""

from __future__ import annotations

import pytest

from dunvyr.identity.infrastructure import tables


@pytest.mark.unit
def test_identity_metadata_contains_only_owned_tables() -> None:
    names = set(tables.metadata.tables)

    assert names == {"identity_guests", "identity_sessions"}
    assert all(name.startswith("identity_") for name in names)


@pytest.mark.unit
def test_identity_session_schema_stores_only_a_unique_token_hash() -> None:
    session_table = tables.sessions

    assert session_table.c.token_hash.unique
    assert not session_table.c.token_hash.nullable
    assert "token" not in session_table.c
    foreign_keys = list(session_table.c.guest_id.foreign_keys)
    assert [fk.target_fullname for fk in foreign_keys] == ["identity_guests.id"]

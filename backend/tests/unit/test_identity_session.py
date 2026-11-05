"""Unit tests for guest and server-side session invariants (identity domain)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from dunvyr.identity.domain.guest import Guest
from dunvyr.identity.domain.nickname import Nickname
from dunvyr.identity.domain.session import (
    SESSION_LIFETIME,
    GuestSession,
    hash_session_token,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
GUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")


@pytest.mark.unit
def test_guest_keeps_identity_nickname_and_creation_time() -> None:
    guest = Guest(id=GUEST_ID, nickname=Nickname.parse("Alice"), created_at=NOW)

    assert guest.id == GUEST_ID
    assert guest.nickname.value == "Alice"
    assert guest.created_at == NOW


@pytest.mark.unit
def test_guest_rejects_naive_creation_time() -> None:
    with pytest.raises(ValueError, match="timezone"):
        Guest(id=GUEST_ID, nickname=Nickname.parse("Alice"), created_at=datetime(2026, 1, 1))


@pytest.mark.unit
def test_session_lifetime_is_30_days() -> None:
    assert timedelta(days=30) == SESSION_LIFETIME


@pytest.mark.unit
def test_session_expires_fixed_lifetime_after_creation() -> None:
    session = GuestSession.create(
        id=SESSION_ID,
        guest_id=GUEST_ID,
        token_hash=hash_session_token("token"),
        created_at=NOW,
    )

    assert session.id == SESSION_ID
    assert session.guest_id == GUEST_ID
    assert session.created_at == NOW
    assert session.expires_at == NOW + timedelta(days=30)


@pytest.mark.unit
def test_session_is_valid_strictly_before_expiration() -> None:
    session = GuestSession.create(
        id=SESSION_ID,
        guest_id=GUEST_ID,
        token_hash=hash_session_token("token"),
        created_at=NOW,
    )

    assert session.is_valid_at(NOW)
    assert session.is_valid_at(session.expires_at - timedelta(microseconds=1))
    assert not session.is_valid_at(session.expires_at)
    assert not session.is_valid_at(session.expires_at + timedelta(seconds=1))


@pytest.mark.unit
def test_session_token_hash_is_sha256_hex_and_never_the_raw_token() -> None:
    # Published SHA-256 test vector for "abc": the domain stores a one-way hash,
    # so a leaked database cannot be replayed as a session credential.
    assert (
        hash_session_token("abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
    assert hash_session_token("opaque-session-token") not in {"abc", "opaque-session-token"}


@pytest.mark.unit
def test_session_requires_timezone_aware_timestamps() -> None:
    with pytest.raises(ValueError, match="timezone"):
        GuestSession(
            id=SESSION_ID,
            guest_id=GUEST_ID,
            token_hash=hash_session_token("token"),
            created_at=datetime(2026, 1, 1),
            expires_at=datetime(2026, 1, 31),
        )

"""Unit tests for identity application use cases with in-memory fakes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from dunvyr.identity.application.service import IdentityService
from dunvyr.identity.domain.guest import Guest
from dunvyr.identity.domain.nickname import InvalidNickname
from dunvyr.identity.domain.session import GuestSession, hash_session_token
from dunvyr.identity.public import GuestResolver

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
GUEST_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
RAW_TOKEN = "raw-opaque-token"


class FakeGuestRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, Guest] = {}

    def add(self, guest: Guest) -> None:
        self.rows[guest.id] = guest

    def get(self, guest_id: UUID) -> Guest | None:
        return self.rows.get(guest_id)


class FakeSessionRepository:
    def __init__(self) -> None:
        self.rows: list[GuestSession] = []

    def add(self, session: GuestSession) -> None:
        self.rows.append(session)

    def find_by_token_hash(self, token_hash: str) -> GuestSession | None:
        return next((row for row in self.rows if row.token_hash == token_hash), None)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.guests = FakeGuestRepository()
        self.sessions = FakeSessionRepository()
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class SequenceIdFactory:
    def __init__(self, *values: UUID) -> None:
        self._values = list(values)

    def __call__(self) -> UUID:
        return self._values.pop(0)


class FixedTokenGenerator:
    def __init__(self, token: str) -> None:
        self.token = token
        self.calls = 0

    def generate(self) -> str:
        self.calls += 1
        return self.token


def build_service(
    *,
    uow: FakeUnitOfWork | None = None,
    clock: FixedClock | None = None,
    token: str = RAW_TOKEN,
) -> tuple[IdentityService, FakeUnitOfWork]:
    resolved_uow = uow or FakeUnitOfWork()
    service = IdentityService(
        unit_of_work=resolved_uow,
        token_generator=FixedTokenGenerator(token),
        clock=clock or FixedClock(NOW),
        id_factory=SequenceIdFactory(GUEST_ID, SESSION_ID),
    )
    return service, resolved_uow


@pytest.mark.unit
def test_service_satisfies_public_guest_resolver_contract() -> None:
    service, _uow = build_service()

    assert isinstance(service, GuestResolver)


@pytest.mark.unit
def test_create_session_persists_guest_and_commits() -> None:
    service, uow = build_service()

    issued = service.create_session("  Alice ")

    assert issued.token == RAW_TOKEN
    assert issued.guest.id == GUEST_ID
    assert issued.guest.nickname == "Alice"
    assert uow.commits == 1
    assert list(uow.guests.rows) == [GUEST_ID]
    assert uow.guests.rows[GUEST_ID].nickname.value == "Alice"
    assert uow.guests.rows[GUEST_ID].created_at == NOW


@pytest.mark.unit
def test_create_session_stores_only_the_token_hash() -> None:
    service, uow = build_service()

    service.create_session("Alice")

    stored = uow.sessions.rows[0]
    assert stored.id == SESSION_ID
    assert stored.guest_id == GUEST_ID
    assert stored.token_hash == hash_session_token(RAW_TOKEN)
    assert RAW_TOKEN not in {stored.token_hash}
    assert stored.created_at == NOW
    assert stored.expires_at == NOW + timedelta(days=30)


@pytest.mark.unit
def test_create_session_returns_domain_validation_error_for_bad_nickname() -> None:
    service, uow = build_service()

    with pytest.raises(InvalidNickname):
        service.create_session("   ")

    assert uow.commits == 0
    assert uow.guests.rows == {}


@pytest.mark.unit
def test_create_session_allows_duplicate_nicknames() -> None:
    service = IdentityService(
        unit_of_work=FakeUnitOfWork(),
        token_generator=FixedTokenGenerator(RAW_TOKEN),
        clock=FixedClock(NOW),
        id_factory=iter([GUEST_ID, SESSION_ID, uuid4(), uuid4()]).__next__,
    )

    first = service.create_session("Alice")
    second = service.create_session("Alice")

    assert first.guest.id != second.guest.id
    assert first.guest.nickname == second.guest.nickname == "Alice"


@pytest.mark.unit
def test_resolve_guest_returns_snapshot_for_valid_session() -> None:
    service, _uow = build_service()
    issued = service.create_session("Alice")

    assert service.resolve_guest(issued.token) == issued.guest


@pytest.mark.unit
@pytest.mark.parametrize("token", [None, ""])
def test_resolve_guest_without_token_returns_none(token: str | None) -> None:
    service, _uow = build_service()

    assert service.resolve_guest(token) is None


@pytest.mark.unit
def test_resolve_guest_with_unknown_token_returns_none() -> None:
    service, _uow = build_service()
    service.create_session("Alice")

    assert service.resolve_guest("unrelated-token") is None


@pytest.mark.unit
def test_resolve_guest_treats_expired_session_as_missing() -> None:
    clock = FixedClock(NOW)
    service, _uow = build_service(clock=clock)
    issued = service.create_session("Alice")

    clock.now = NOW + timedelta(days=30)

    assert service.resolve_guest(issued.token) is None


@pytest.mark.unit
def test_resolve_guest_works_until_expiration_boundary() -> None:
    clock = FixedClock(NOW)
    service, _uow = build_service(clock=clock)
    issued = service.create_session("Alice")

    clock.now = NOW + timedelta(days=30) - timedelta(microseconds=1)

    assert service.resolve_guest(issued.token) == issued.guest

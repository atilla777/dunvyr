"""Identity application use cases: create and resolve guest sessions."""

from __future__ import annotations

from dataclasses import dataclass

from dunvyr.identity.application.ports import Clock, IdFactory, TokenGenerator, UnitOfWork
from dunvyr.identity.domain.guest import Guest
from dunvyr.identity.domain.nickname import Nickname
from dunvyr.identity.domain.session import GuestSession, hash_session_token
from dunvyr.identity.public import GuestSnapshot


@dataclass(frozen=True, slots=True)
class IssuedSession:
    """Internal result of ``create_session``: raw token plus the guest snapshot."""

    token: str
    guest: GuestSnapshot


class IdentityService:
    """Application service implementing the identity use cases."""

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        token_generator: TokenGenerator,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._token_generator = token_generator
        self._clock = clock
        self._id_factory = id_factory

    def create_session(self, raw_nickname: str) -> IssuedSession:
        """Create a guest identity and its server-side session atomically."""
        nickname = Nickname.parse(raw_nickname)
        now = self._clock()

        guest = Guest(id=self._id_factory(), nickname=nickname, created_at=now)
        self._unit_of_work.guests.add(guest)

        token = self._token_generator.generate()
        session = GuestSession.create(
            id=self._id_factory(),
            guest_id=guest.id,
            token_hash=hash_session_token(token),
            created_at=now,
        )
        self._unit_of_work.sessions.add(session)
        self._unit_of_work.commit()

        return IssuedSession(
            token=token,
            guest=GuestSnapshot(id=guest.id, nickname=nickname.value),
        )

    def resolve_guest(self, session_token: str | None) -> GuestSnapshot | None:
        """Resolve a raw cookie token; expired sessions behave as missing."""
        if not session_token:
            return None

        session = self._unit_of_work.sessions.find_by_token_hash(hash_session_token(session_token))
        if session is None or not session.is_valid_at(self._clock()):
            return None

        guest = self._unit_of_work.guests.get(session.guest_id)
        if guest is None:
            return None

        return GuestSnapshot(id=guest.id, nickname=guest.nickname.value)

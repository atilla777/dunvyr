"""SQLAlchemy Core repositories translating between rows and domain objects."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from dunvyr.identity.domain.guest import Guest
from dunvyr.identity.domain.nickname import Nickname
from dunvyr.identity.domain.session import GuestSession
from dunvyr.identity.infrastructure import tables


def _to_text(value: datetime) -> str:
    return value.isoformat()


def _from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqlAlchemyGuestRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, guest: Guest) -> None:
        self._session.execute(
            tables.guests.insert().values(
                id=str(guest.id),
                nickname=guest.nickname.value,
                created_at=_to_text(guest.created_at),
            )
        )

    def get(self, guest_id: UUID) -> Guest | None:
        row = (
            self._session.execute(select(tables.guests).where(tables.guests.c.id == str(guest_id)))
            .mappings()
            .first()
        )
        if row is None:
            return None
        return Guest(
            id=UUID(row["id"]),
            nickname=Nickname.parse(row["nickname"]),
            created_at=_from_text(row["created_at"]),
        )


class SqlAlchemySessionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, session: GuestSession) -> None:
        self._session.execute(
            tables.sessions.insert().values(
                id=str(session.id),
                token_hash=session.token_hash,
                guest_id=str(session.guest_id),
                created_at=_to_text(session.created_at),
                expires_at=_to_text(session.expires_at),
            )
        )

    def find_by_token_hash(self, token_hash: str) -> GuestSession | None:
        row = (
            self._session.execute(
                select(tables.sessions).where(tables.sessions.c.token_hash == token_hash)
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return GuestSession(
            id=UUID(row["id"]),
            guest_id=UUID(row["guest_id"]),
            token_hash=row["token_hash"],
            created_at=_from_text(row["created_at"]),
            expires_at=_from_text(row["expires_at"]),
        )


class SqlAlchemyUnitOfWork:
    """One short transaction for a single identity use case."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._guests = SqlAlchemyGuestRepository(session)
        self._sessions = SqlAlchemySessionRepository(session)

    @property
    def guests(self) -> SqlAlchemyGuestRepository:
        return self._guests

    @property
    def sessions(self) -> SqlAlchemySessionRepository:
        return self._sessions

    def commit(self) -> None:
        self._session.commit()

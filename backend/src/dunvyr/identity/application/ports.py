"""Ports the identity application layer depends on."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from dunvyr.identity.domain.guest import Guest
from dunvyr.identity.domain.session import GuestSession

Clock = Callable[[], datetime]
IdFactory = Callable[[], UUID]


class GuestRepository(Protocol):
    def add(self, guest: Guest) -> None: ...

    def get(self, guest_id: UUID) -> Guest | None: ...


class SessionRepository(Protocol):
    def add(self, session: GuestSession) -> None: ...

    def find_by_token_hash(self, token_hash: str) -> GuestSession | None: ...


class UnitOfWork(Protocol):
    @property
    def guests(self) -> GuestRepository: ...

    @property
    def sessions(self) -> SessionRepository: ...

    def commit(self) -> None: ...


class TokenGenerator(Protocol):
    def generate(self) -> str: ...

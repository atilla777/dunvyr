"""Composition of the identity application service for one request."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from dunvyr.identity.application.service import IdentityService
from dunvyr.identity.infrastructure.clock import utc_now
from dunvyr.identity.infrastructure.repositories import SqlAlchemyUnitOfWork
from dunvyr.identity.infrastructure.tokens import SecretsTokenGenerator


def build_identity_service(session: Session) -> IdentityService:
    """Wire concrete adapters into the application service (one per request)."""
    return IdentityService(
        unit_of_work=SqlAlchemyUnitOfWork(session),
        token_generator=SecretsTokenGenerator(),
        clock=utc_now,
        id_factory=uuid4,
    )

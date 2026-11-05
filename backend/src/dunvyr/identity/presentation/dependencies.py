"""FastAPI dependencies wiring identity use cases into HTTP handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from dunvyr.identity.application.service import IdentityService
from dunvyr.infrastructure.db import get_session


def get_identity_service(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> IdentityService:
    factory: Callable[[Session], IdentityService] = request.app.state.identity_service_factory
    return factory(session)

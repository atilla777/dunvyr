"""FastAPI dependencies wiring communication use cases and identity contract."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from dunvyr.communication.application.service import ChatService
from dunvyr.identity.public import SESSION_COOKIE_NAME, GuestResolver, GuestSnapshot
from dunvyr.infrastructure.db import get_session


def get_chat_service(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> ChatService:
    factory: Callable[[Session], ChatService] = request.app.state.chat_service_factory
    return factory(session)


def get_current_guest(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> GuestSnapshot:
    """Resolve the cookie session through identity's public protocol only."""
    resolver_factory: Callable[[Session], GuestResolver] = request.app.state.guest_resolver_factory
    guest = resolver_factory(session).resolve_guest(request.cookies.get(SESSION_COOKIE_NAME))
    if guest is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        )
    return guest


__all__ = ["SESSION_COOKIE_NAME", "get_chat_service", "get_current_guest"]

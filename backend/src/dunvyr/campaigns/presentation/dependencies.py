"""FastAPI dependencies wiring campaign use cases and identity's public contract."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from dunvyr.campaigns.application.service import CampaignService
from dunvyr.campaigns.public import CampaignEventPublisher
from dunvyr.identity.public import SESSION_COOKIE_NAME, GuestResolver, GuestSnapshot
from dunvyr.infrastructure.db import get_session


def get_campaign_service(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> CampaignService:
    factory: Callable[..., CampaignService] = request.app.state.campaign_service_factory
    publisher: CampaignEventPublisher = request.app.state.campaign_event_publisher
    return factory(session, event_publisher=publisher)


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

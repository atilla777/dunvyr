"""Member-visible adventure state."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from dunvyr.adventures.application.service import AdventureReader, AdventureSelector, SelectionError
from dunvyr.identity.public import SESSION_COOKIE_NAME, GuestResolver
from dunvyr.infrastructure.db import get_session


class SafeValidationRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def safe_handler(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(status_code=422, detail="invalid_request") from error

        return safe_handler


router = APIRouter(prefix="/api/campaigns", tags=["adventures"], route_class=SafeValidationRoute)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    adventure_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


def guest_id(request: Request, session: Session) -> UUID:
    resolver: Callable[[Session], GuestResolver] = request.app.state.guest_resolver_factory
    guest = resolver(session).resolve_guest(request.cookies.get(SESSION_COOKIE_NAME))
    if guest is None:
        raise HTTPException(status_code=403, detail="forbidden")
    return guest.id


@router.get("/{campaign_id}/adventures")
def catalog(
    campaign_id: UUID, request: Request, session: Annotated[Session, Depends(get_session)]
) -> dict[str, object]:
    factory: Callable[[Session], AdventureSelector] = request.app.state.adventure_selector_factory
    try:
        return {"adventures": factory(session).catalog(campaign_id, guest_id(request, session))}
    except SelectionError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error


@router.post("/{campaign_id}/adventure")
def select_adventure(
    campaign_id: UUID,
    payload: Selection,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    origin = request.headers.get("origin")
    if origin is None or not request.app.state.allowed_origins.contains(origin):
        raise HTTPException(status_code=403, detail="Origin not allowed")
    client = request.client.host if request.client else "unknown"
    retry = request.app.state.adventure_rate_limiter.hit(client)
    if retry is not None:
        raise HTTPException(
            status_code=429, detail="rate_limited", headers={"Retry-After": str(retry)}
        )
    factory: Callable[[Session], AdventureSelector] = request.app.state.adventure_selector_factory
    try:
        status, result = factory(session).select(
            campaign_id, guest_id(request, session), payload.adventure_id, payload.fingerprint
        )
    except SelectionError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    response.status_code = status
    return result


@router.get("/{campaign_id}/adventure")
def get_adventure(
    campaign_id: UUID,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    resolver: Callable[[Session], GuestResolver] = request.app.state.guest_resolver_factory
    guest = resolver(session).resolve_guest(request.cookies.get(SESSION_COOKIE_NAME))
    if guest is None:
        raise HTTPException(status_code=403, detail="forbidden")
    factory: Callable[[Session], AdventureReader] = request.app.state.adventure_reader_factory
    try:
        return factory(session).read(campaign_id, guest.id)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail="forbidden") from error

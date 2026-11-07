"""Character HTTP boundary."""

from collections.abc import Callable, Coroutine
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from pydantic import BaseModel, ConfigDict, model_validator
from sqlalchemy.orm import Session

from dunvyr.characters.application.service import CharacterError, CharacterService
from dunvyr.identity.public import SESSION_COOKIE_NAME, GuestResolver
from dunvyr.infrastructure.db import get_session


class SafeRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handler = super().get_route_handler()

        async def safe(request: Request) -> Response:
            try:
                return await handler(request)
            except RequestValidationError as error:
                raise HTTPException(status_code=422, detail="invalid_request") from error

        return safe


router = APIRouter(prefix="/api/campaigns", tags=["characters"], route_class=SafeRoute)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class CharacteristicInput(StrictModel):
    strength: int
    agility: int
    intellect: int
    presence: int


class AllocationInput(StrictModel):
    characteristics: CharacteristicInput
    skills: dict[str, int]


class CharacterInput(StrictModel):
    name: str
    appearance: str
    archetype_id: str
    allocation: AllocationInput | None = None

    @model_validator(mode="before")
    @classmethod
    def reject_null_allocation(cls, value: Any) -> Any:
        if isinstance(value, dict) and "allocation" in value and value["allocation"] is None:
            raise ValueError("allocation must not be null")
        return value


def actor(request: Request, session: Session) -> UUID:
    resolver: Callable[[Session], GuestResolver] = request.app.state.guest_resolver_factory
    guest = resolver(session).resolve_guest(request.cookies.get(SESSION_COOKIE_NAME))
    if guest is None:
        raise HTTPException(status_code=403, detail="forbidden")
    return guest.id


def service(request: Request, session: Session) -> CharacterService:
    factory: Callable[[Session], CharacterService] = request.app.state.character_service_factory
    return factory(session)


@router.get("/{campaign_id}/character-templates")
def choices(
    campaign_id: UUID, request: Request, session: Annotated[Session, Depends(get_session)]
) -> dict[str, object]:
    try:
        return service(request, session).choices(campaign_id, actor(request, session))
    except CharacterError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error


@router.get("/{campaign_id}/character")
def read_character(
    campaign_id: UUID, request: Request, session: Annotated[Session, Depends(get_session)]
) -> dict[str, object] | None:
    try:
        return service(request, session).get(campaign_id, actor(request, session))
    except CharacterError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error


@router.post("/{campaign_id}/character")
def create_character(
    campaign_id: UUID,
    payload: CharacterInput,
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, object]:
    origin = request.headers.get("origin")
    if origin is None or not request.app.state.allowed_origins.contains(origin):
        raise HTTPException(status_code=403, detail="Origin not allowed")
    client = request.client.host if request.client else "unknown"
    retry = request.app.state.character_rate_limiter.hit(client)
    if retry is not None:
        raise HTTPException(
            status_code=429, detail="rate_limited", headers={"Retry-After": str(retry)}
        )
    try:
        status, result = service(request, session).create(
            campaign_id,
            actor(request, session),
            payload.name,
            payload.appearance,
            payload.archetype_id,
            payload.allocation.model_dump() if payload.allocation is not None else None,
        )
    except CharacterError as error:
        raise HTTPException(status_code=error.status, detail=error.detail) from error
    response.status_code = status
    return result

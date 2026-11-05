"""Identity REST endpoints: create a guest session and read the current guest."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from dunvyr.identity.application.service import IdentityService
from dunvyr.identity.domain.nickname import InvalidNickname
from dunvyr.identity.domain.session import SESSION_LIFETIME
from dunvyr.identity.presentation.config import SESSION_COOKIE_NAME
from dunvyr.identity.presentation.dependencies import get_identity_service
from dunvyr.identity.presentation.schemas import CreateSessionRequest, GuestResponse
from dunvyr.identity.presentation.security import enforce_rate_limit, require_allowed_origin

router = APIRouter(prefix="/api/identity", tags=["identity"])

Service = Annotated[IdentityService, Depends(get_identity_service)]


@router.post(
    "/sessions",
    status_code=status.HTTP_201_CREATED,
    response_model=GuestResponse,
    dependencies=[Depends(require_allowed_origin), Depends(enforce_rate_limit)],
)
def create_session(
    payload: CreateSessionRequest,
    request: Request,
    response: Response,
    service: Service,
) -> GuestResponse:
    """Create a guest identity and set the opaque session cookie."""
    try:
        issued = service.create_session(payload.nickname)
    except InvalidNickname as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=issued.token,
        max_age=int(SESSION_LIFETIME.total_seconds()),
        httponly=True,
        samesite="lax",
        secure=bool(request.app.state.cookie_secure),
        path="/",
    )
    return GuestResponse(id=issued.guest.id, nickname=issued.guest.nickname)


@router.get("/me", response_model=GuestResponse)
def current_guest(request: Request, service: Service) -> GuestResponse:
    """Return the guest bound to a valid session cookie, or 401."""
    guest = service.resolve_guest(request.cookies.get(SESSION_COOKIE_NAME))
    if guest is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return GuestResponse(id=guest.id, nickname=guest.nickname)

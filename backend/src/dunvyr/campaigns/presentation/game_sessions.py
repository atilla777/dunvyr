"""Strict lifecycle HTTP boundary."""

from dataclasses import asdict
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from dunvyr.campaigns.application.errors import CampaignAccessDenied, CampaignNotFound
from dunvyr.campaigns.application.game_sessions import (
    GameSessionService,
    SessionCommand,
    SessionConflict,
)
from dunvyr.campaigns.domain.game_session import InvalidGameSessionAction
from dunvyr.campaigns.presentation.dependencies import get_current_guest
from dunvyr.campaigns.presentation.security import require_allowed_origin
from dunvyr.identity.public import GuestSnapshot
from dunvyr.infrastructure.db import get_session

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])


class SessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Annotated[StrictInt, Field(ge=0)]


class SessionSnapshotResponse(BaseModel):
    id: UUID
    status: Literal["running", "paused", "ended"]
    started_at: datetime
    ended_at: datetime | None


class SessionStateResponse(BaseModel):
    revision: int
    session: SessionSnapshotResponse | None


class SessionCommandResponse(SessionStateResponse):
    replayed: bool


def get_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> GameSessionService:
    service: GameSessionService = request.app.state.game_session_service_factory(session)
    return service


def rate_limit(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    retry = request.app.state.game_session_rate_limiter.hit(client)
    if retry is not None:
        raise HTTPException(
            429, "Too many game session commands", headers={"Retry-After": str(retry)}
        )


Service = Annotated[GameSessionService, Depends(get_service)]
Guest = Annotated[GuestSnapshot, Depends(get_current_guest)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


def http_error(error: Exception) -> HTTPException:
    if isinstance(error, CampaignNotFound):
        return HTTPException(404, "not_found")
    if isinstance(error, CampaignAccessDenied):
        return HTTPException(403, "forbidden")
    return HTTPException(
        409, str(error) if isinstance(error, SessionConflict) else "invalid_action"
    )


@router.get("/{campaign_id}/game-session", response_model=SessionStateResponse)
def get_state(campaign_id: UUID, guest: Guest, service: Service) -> dict[str, object]:
    try:
        return asdict(service.get(campaign_id, guest.id))
    except (CampaignNotFound, CampaignAccessDenied) as error:
        raise http_error(error) from error


def execute(
    campaign_id: UUID,
    session_id: UUID | None,
    action: str,
    payload: SessionRequest,
    guest: GuestSnapshot,
    service: GameSessionService,
    key: UUID,
    response: Response,
) -> dict[str, object]:
    try:
        state, replayed = service.execute(
            SessionCommand(
                campaign_id, guest.id, key, payload.expected_revision, action, session_id
            )
        )
    except (
        CampaignNotFound,
        CampaignAccessDenied,
        SessionConflict,
        InvalidGameSessionAction,
    ) as error:
        raise http_error(error) from error
    response.status_code = 201 if action == "start" and not replayed else 200
    return {**asdict(state), "replayed": replayed}


@router.post(
    "/{campaign_id}/game-session/start",
    response_model=SessionCommandResponse,
    dependencies=[Depends(require_allowed_origin), Depends(rate_limit)],
)
def start(
    campaign_id: UUID,
    payload: SessionRequest,
    guest: Guest,
    service: Service,
    key: Key,
    response: Response,
) -> dict[str, object]:
    return execute(campaign_id, None, "start", payload, guest, service, key, response)


@router.post(
    "/{campaign_id}/game-session/{session_id}/{action}",
    response_model=SessionCommandResponse,
    dependencies=[Depends(require_allowed_origin), Depends(rate_limit)],
)
def transition(
    campaign_id: UUID,
    session_id: UUID,
    action: Literal["pause", "resume", "end"],
    payload: SessionRequest,
    guest: Guest,
    service: Service,
    key: Key,
    response: Response,
) -> dict[str, object]:
    return execute(campaign_id, session_id, action, payload, guest, service, key, response)

"""Member-only strict start/read queue API."""

from dataclasses import asdict, dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from dunvyr.gameplay.application.service import QueueCommand, QueueError, QueueService
from dunvyr.gameplay.public import QueueState
from dunvyr.identity.public import SESSION_COOKIE_NAME, GuestSnapshot
from dunvyr.infrastructure.db import get_session

router = APIRouter(prefix="/api/campaigns", tags=["gameplay"])


@dataclass(frozen=True)
class CommandResponse(QueueState):
    replayed: bool


class SwapRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[StrictInt, Field(ge=1)]
    expected_lifecycle_revision: Annotated[StrictInt, Field(ge=0)]
    target_guest_id: UUID


class StartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Annotated[StrictInt, Field(ge=0)]
    expected_lifecycle_revision: Annotated[StrictInt, Field(ge=0)]
    character_id: UUID
    encounter_id: Annotated[str, Field(min_length=1, max_length=128)]


def guest(request: Request, session: Annotated[Session, Depends(get_session)]) -> GuestSnapshot:
    resolved: GuestSnapshot | None = request.app.state.guest_resolver_factory(
        session
    ).resolve_guest(request.cookies.get(SESSION_COOKIE_NAME))
    if resolved is None:
        raise HTTPException(403, "forbidden")
    return resolved


def service(request: Request, session: Annotated[Session, Depends(get_session)]) -> QueueService:
    result: QueueService = request.app.state.queue_service_factory(session)
    return result


def mutation(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None or not request.app.state.allowed_origins.contains(origin):
        raise HTTPException(403, "forbidden")
    retry = request.app.state.queue_rate_limiter.hit(
        request.client.host if request.client else "unknown"
    )
    if retry is not None:
        raise HTTPException(429, "Too many queue commands", headers={"Retry-After": str(retry)})


Guest = Annotated[GuestSnapshot, Depends(guest)]
Service = Annotated[QueueService, Depends(service)]
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


@router.get("/{campaign_id}/queue", response_model=QueueState)
def get_queue(
    campaign_id: UUID, actor: Guest, use_case: Service, response: Response
) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return asdict(use_case.get(campaign_id, actor.id))
    except QueueError as error:
        raise HTTPException(error.status, error.detail) from error


@router.post(
    "/{campaign_id}/queue/start", response_model=CommandResponse, dependencies=[Depends(mutation)]
)
def start(
    campaign_id: UUID,
    payload: StartRequest,
    actor: Guest,
    use_case: Service,
    key: Key,
    response: Response,
) -> dict[str, object]:
    try:
        state, replayed = use_case.execute(
            QueueCommand(
                campaign_id,
                actor.id,
                key,
                payload.expected_version,
                payload.expected_lifecycle_revision,
                "start",
                payload.character_id,
                payload.encounter_id,
            )
        )
    except QueueError as error:
        raise HTTPException(error.status, error.detail) from error
    response.headers["Cache-Control"] = "private, no-store"
    response.status_code = 200 if replayed else 201
    return {**asdict(state), "replayed": replayed}


@router.post(
    "/{campaign_id}/queue/swap", response_model=CommandResponse, dependencies=[Depends(mutation)]
)
def swap(
    campaign_id: UUID,
    payload: SwapRequest,
    actor: Guest,
    use_case: Service,
    key: Key,
    response: Response,
) -> dict[str, object]:
    try:
        state, replayed = use_case.execute(
            QueueCommand(
                campaign_id,
                actor.id,
                key,
                payload.expected_version,
                payload.expected_lifecycle_revision,
                "swap",
                target_guest_id=payload.target_guest_id,
            )
        )
    except QueueError as error:
        raise HTTPException(error.status, error.detail) from error
    response.headers["Cache-Control"] = "private, no-store"
    return {**asdict(state), "replayed": replayed}

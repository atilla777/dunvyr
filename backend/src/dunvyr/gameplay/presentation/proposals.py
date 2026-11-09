"""Strict member-only private proposal HTTP boundary."""

from dataclasses import asdict, dataclass
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr
from sqlalchemy.orm import Session

from dunvyr.gameplay.application.confirmation import ConfirmationService
from dunvyr.gameplay.application.proposals import ProposalCommand, ProposalService, ProposalState
from dunvyr.gameplay.application.service import QueueError
from dunvyr.gameplay.presentation.router import Guest, Key
from dunvyr.infrastructure.db import get_session

router = APIRouter(prefix="/api/campaigns", tags=["gameplay"])
Version = Annotated[StrictInt, Field(ge=0)]
ScenarioId = Annotated[StrictStr, Field(min_length=1, max_length=128)]


class Versions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: Version
    expected_queue_version: Version
    expected_lifecycle_revision: Version


class EditRequest(Versions):
    encounter_id: ScenarioId
    object_id: ScenarioId
    solution_id: ScenarioId


class CreateRequest(EditRequest):
    character_id: UUID


@dataclass(frozen=True)
class CommandResponse(ProposalState):
    replayed: bool


def service(request: Request, session: Annotated[Session, Depends(get_session)]) -> ProposalService:
    result: ProposalService = request.app.state.proposal_service_factory(session)
    return result


def mutation(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None or not request.app.state.allowed_origins.contains(origin):
        raise HTTPException(403, "forbidden")
    retry = request.app.state.proposal_rate_limiter.hit(
        request.client.host if request.client else "unknown"
    )
    if retry is not None:
        raise HTTPException(429, "Too many proposal commands", headers={"Retry-After": str(retry)})


Service = Annotated[ProposalService, Depends(service)]


@router.get("/{campaign_id}/proposals", response_model=ProposalState)
def get_proposals(
    campaign_id: UUID, actor: Guest, use_case: Service, response: Response
) -> dict[str, object]:
    response.headers["Cache-Control"] = "private, no-store"
    try:
        return asdict(use_case.get(campaign_id, actor.id))
    except QueueError as error:
        raise HTTPException(error.status, error.detail) from error


def run(
    use_case: ProposalService, command: ProposalCommand, response: Response
) -> dict[str, object]:
    try:
        state, replayed = use_case.execute(command)
    except QueueError as error:
        raise HTTPException(error.status, error.detail) from error
    response.headers["Cache-Control"] = "private, no-store"
    response.status_code = 201 if command.action == "create" and not replayed else 200
    return {**asdict(state), "replayed": replayed}


@router.post(
    "/{campaign_id}/proposals", response_model=CommandResponse, dependencies=[Depends(mutation)]
)
def create(
    campaign_id: UUID,
    payload: CreateRequest,
    actor: Guest,
    use_case: Service,
    key: Key,
    response: Response,
) -> dict[str, object]:
    return run(
        use_case,
        ProposalCommand(
            campaign_id,
            actor.id,
            key,
            payload.expected_version,
            payload.expected_queue_version,
            payload.expected_lifecycle_revision,
            "create",
            character_id=payload.character_id,
            encounter_id=payload.encounter_id,
            object_id=payload.object_id,
            solution_id=payload.solution_id,
        ),
        response,
    )


@router.post(
    "/{campaign_id}/proposals/{proposal_id}/edit",
    response_model=CommandResponse,
    dependencies=[Depends(mutation)],
)
def edit(
    campaign_id: UUID,
    proposal_id: UUID,
    payload: EditRequest,
    actor: Guest,
    use_case: Service,
    key: Key,
    response: Response,
) -> dict[str, object]:
    return run(
        use_case,
        ProposalCommand(
            campaign_id,
            actor.id,
            key,
            payload.expected_version,
            payload.expected_queue_version,
            payload.expected_lifecycle_revision,
            "edit",
            proposal_id,
            encounter_id=payload.encounter_id,
            object_id=payload.object_id,
            solution_id=payload.solution_id,
        ),
        response,
    )


@router.post(
    "/{campaign_id}/proposals/{proposal_id}/cancel",
    response_model=CommandResponse,
    dependencies=[Depends(mutation)],
)
def cancel(
    campaign_id: UUID,
    proposal_id: UUID,
    payload: Versions,
    actor: Guest,
    use_case: Service,
    key: Key,
    response: Response,
) -> dict[str, object]:
    return run(
        use_case,
        ProposalCommand(
            campaign_id,
            actor.id,
            key,
            payload.expected_version,
            payload.expected_queue_version,
            payload.expected_lifecycle_revision,
            "cancel",
            proposal_id,
        ),
        response,
    )


def confirmation_service(
    request: Request, session: Annotated[Session, Depends(get_session)]
) -> ConfirmationService:
    result: ConfirmationService = request.app.state.confirmation_service_factory(session)
    return result


Confirmation = Annotated[ConfirmationService, Depends(confirmation_service)]


@router.post("/{campaign_id}/proposals/{proposal_id}/confirm", dependencies=[Depends(mutation)])
def confirm(
    campaign_id: UUID,
    proposal_id: UUID,
    payload: Versions,
    actor: Guest,
    use_case: Confirmation,
    key: Key,
    response: Response,
) -> dict[str, object]:
    try:
        result, replayed = use_case.execute(
            ProposalCommand(
                campaign_id,
                actor.id,
                key,
                payload.expected_version,
                payload.expected_queue_version,
                payload.expected_lifecycle_revision,
                "confirm",
                proposal_id,
            )
        )
    except QueueError as error:
        raise HTTPException(error.status, error.detail) from error
    response.headers["Cache-Control"] = "private, no-store"
    return {"result": result, "replayed": replayed}


@router.get("/{campaign_id}/check-result")
def latest_check(
    campaign_id: UUID, actor: Guest, use_case: Confirmation, response: Response
) -> dict[str, object]:
    try:
        result = use_case.latest(campaign_id, actor.id)
    except QueueError as error:
        raise HTTPException(error.status, error.detail) from error
    response.headers["Cache-Control"] = "private, no-store"
    return {"result": result}

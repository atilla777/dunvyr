"""Member-only retry: never calls a gameplay command or a provider."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictInt
from sqlalchemy.orm import Session

from dunvyr.communication.infrastructure.narrations import NarrationConflict, NarrationRepository
from dunvyr.communication.presentation.dependencies import get_current_guest
from dunvyr.communication.presentation.schemas import NarrationBody
from dunvyr.identity.public import GuestSnapshot
from dunvyr.infrastructure.db import get_session

router = APIRouter(prefix="/api/campaigns", tags=["communication"])


class RetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Annotated[StrictInt, Field(ge=1)]


@router.post("/{campaign_id}/narrations/{result_event_id}/retry", response_model=NarrationBody)
def retry_narration(
    campaign_id: UUID,
    result_event_id: UUID,
    payload: RetryRequest,
    guest: Annotated[GuestSnapshot, Depends(get_current_guest)],
    key: Annotated[UUID, Header(alias="Idempotency-Key")],
    session: Annotated[Session, Depends(get_session)],
    request: Request,
    response: Response,
) -> dict[str, object]:
    origin = request.headers.get("origin")
    if origin is None or not request.app.state.allowed_origins.contains(origin):
        raise HTTPException(403, "forbidden")
    repo = NarrationRepository(session)
    repo.lock()
    member = request.app.state.campaign_membership_reader_factory(session).find_member(
        campaign_id, guest.id
    )
    if member is None:
        raise HTTPException(403, "forbidden")
    try:
        state, event_id = repo.retry(
            campaign_id,
            guest.id,
            result_event_id,
            key,
            payload.expected_revision,
            request.app.state.narration_clock(),
        )
        session.commit()
    except NarrationConflict as error:
        raise HTTPException(
            error.status,
            error.detail,
            headers={"Retry-After": "10"} if error.status == 429 else None,
        ) from error
    if event_id is not None:
        try:
            request.app.state.narration_notify(campaign_id, event_id)
        except Exception:
            logging.getLogger(__name__).warning("Narration retry delivery failed after commit")
    response.headers["Cache-Control"] = "private, no-store"
    return state

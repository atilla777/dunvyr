"""Campaign REST endpoints: create a campaign and read it as a member."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from dunvyr.campaigns.application.errors import (
    CampaignAccessDenied,
    CampaignNotFound,
    InvitationUnavailable,
    NicknameTaken,
    NoFreeSeats,
)
from dunvyr.campaigns.application.service import (
    CampaignService,
    CampaignView,
    CreateCampaign,
    JoinCampaign,
)
from dunvyr.campaigns.domain.max_seats import InvalidMaxSeats
from dunvyr.campaigns.domain.name import InvalidCampaignName
from dunvyr.campaigns.presentation.config import INVITATION_PATH_PREFIX
from dunvyr.campaigns.presentation.dependencies import get_campaign_service, get_current_guest
from dunvyr.campaigns.presentation.schemas import (
    CampaignInvitationResponse,
    CampaignMemberResponse,
    CampaignResponse,
    CreateCampaignRequest,
    JoinCampaignRequest,
)
from dunvyr.campaigns.presentation.security import (
    enforce_campaign_rate_limit,
    enforce_join_rate_limit,
    require_allowed_origin,
)
from dunvyr.identity.public import GuestSnapshot

router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])

Service = Annotated[CampaignService, Depends(get_campaign_service)]
Guest = Annotated[GuestSnapshot, Depends(get_current_guest)]
IdempotencyKey = Annotated[str | None, Header(alias="Idempotency-Key")]


def _to_response(view: CampaignView, invitation_secret: str | None = None) -> CampaignResponse:
    invitation = CampaignInvitationResponse(active=view.invitation_active)
    if invitation_secret is not None:
        invitation.secret = invitation_secret
        invitation.path = f"{INVITATION_PATH_PREFIX}{invitation_secret}"
    return CampaignResponse(
        id=view.id,
        name=view.name,
        max_seats=view.max_seats,
        organizer_id=view.organizer_id,
        created_at=view.created_at,
        members=[
            CampaignMemberResponse(
                guest_id=member.guest_id,
                nickname=member.nickname,
                role=member.role.value,
                joined_at=member.joined_at,
            )
            for member in view.members
        ],
        invitation=invitation,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=CampaignResponse,
    dependencies=[Depends(require_allowed_origin), Depends(enforce_campaign_rate_limit)],
)
def create_campaign(
    payload: CreateCampaignRequest,
    guest: Guest,
    service: Service,
    response: Response,
    idempotency_key: IdempotencyKey = None,
) -> CampaignResponse:
    """Create a campaign once per organizer and idempotency key."""
    if idempotency_key is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key header is required",
        )
    try:
        key = UUID(idempotency_key)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Idempotency-Key header must be a UUID",
        ) from error

    try:
        issued = service.create_campaign(
            CreateCampaign(
                organizer_id=guest.id,
                organizer_nickname=guest.nickname,
                name=payload.name,
                max_seats=payload.max_seats,
                idempotency_key=key,
            )
        )
    except (InvalidCampaignName, InvalidMaxSeats) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error

    response.status_code = status.HTTP_201_CREATED if issued.created else status.HTTP_200_OK
    return _to_response(issued.campaign, issued.invitation_secret)


@router.post(
    "/join",
    status_code=status.HTTP_201_CREATED,
    response_model=CampaignResponse,
    dependencies=[Depends(require_allowed_origin), Depends(enforce_join_rate_limit)],
)
def join_campaign(
    payload: JoinCampaignRequest,
    guest: Guest,
    service: Service,
    response: Response,
) -> CampaignResponse:
    """Join by invitation secret; a repeat join replays the same membership."""
    try:
        joined = service.join_campaign(
            JoinCampaign(
                secret=payload.secret,
                guest_id=guest.id,
                guest_nickname=guest.nickname,
            )
        )
    except InvitationUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not_found",
        ) from error
    except NoFreeSeats as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="campaign_full",
        ) from error
    except NicknameTaken as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="nickname_taken",
        ) from error

    response.status_code = status.HTTP_201_CREATED if joined.joined else status.HTTP_200_OK
    return _to_response(joined.campaign)


@router.get("/{campaign_id}", response_model=CampaignResponse)
def get_campaign(
    campaign_id: UUID,
    guest: Guest,
    service: Service,
) -> CampaignResponse:
    """Return a campaign only to its members; the secret is never repeated."""
    try:
        view = service.get_campaign(campaign_id, guest.id)
    except CampaignNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not_found",
        ) from error
    except CampaignAccessDenied as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from error
    return _to_response(view)


@router.post(
    "/{campaign_id}/invitation/revoke",
    response_model=CampaignResponse,
    dependencies=[Depends(require_allowed_origin), Depends(enforce_campaign_rate_limit)],
)
def revoke_invitation(
    campaign_id: UUID,
    guest: Guest,
    service: Service,
) -> CampaignResponse:
    """Revoke the invitation; only the organizer may do so."""
    try:
        view = service.revoke_invitation(campaign_id, guest.id)
    except CampaignNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="not_found",
        ) from error
    except CampaignAccessDenied as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from error
    return _to_response(view)

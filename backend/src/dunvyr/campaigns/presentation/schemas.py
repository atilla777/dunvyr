"""Pydantic DTOs for the campaigns REST boundary."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from dunvyr.campaigns.domain.max_seats import DEFAULT_MAX_SEATS


class CreateCampaignRequest(BaseModel):
    name: str
    max_seats: int = DEFAULT_MAX_SEATS


class JoinCampaignRequest(BaseModel):
    secret: str = Field(min_length=1)


class CampaignMemberResponse(BaseModel):
    guest_id: UUID
    nickname: str
    role: str
    joined_at: datetime


class CampaignInvitationResponse(BaseModel):
    active: bool
    # The raw secret is only ever populated by a successful create response.
    secret: str | None = None
    path: str | None = None


class CampaignResponse(BaseModel):
    id: UUID
    name: str
    max_seats: int
    organizer_id: UUID
    created_at: datetime
    members: list[CampaignMemberResponse]
    invitation: CampaignInvitationResponse

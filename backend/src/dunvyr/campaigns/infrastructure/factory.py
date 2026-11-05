"""Composition of the campaigns application service for one request."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from dunvyr.campaigns.application.service import CampaignService
from dunvyr.campaigns.infrastructure.clock import utc_now
from dunvyr.campaigns.infrastructure.repositories import SqlAlchemyUnitOfWork
from dunvyr.campaigns.infrastructure.tokens import SecretsInvitationSecretGenerator


def build_campaign_service(session: Session) -> CampaignService:
    """Wire concrete adapters into the application service (one per request)."""
    return CampaignService(
        unit_of_work=SqlAlchemyUnitOfWork(session),
        invitation_secret_generator=SecretsInvitationSecretGenerator(),
        clock=utc_now,
        id_factory=uuid4,
    )

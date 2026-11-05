"""Composition of the communication application services for one session."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy.orm import Session

from dunvyr.campaigns.public import CampaignMembershipReader
from dunvyr.communication.application.service import ChatService, MemberEventService
from dunvyr.communication.infrastructure.clock import utc_now
from dunvyr.communication.infrastructure.repositories import SqlAlchemyChatUnitOfWork


def build_chat_service(
    session: Session,
    *,
    membership_reader: CampaignMembershipReader,
) -> ChatService:
    """Wire chat use cases with campaigns' public membership reader."""
    return ChatService(
        unit_of_work=SqlAlchemyChatUnitOfWork(session),
        membership_reader=membership_reader,
        clock=utc_now,
        id_factory=uuid4,
    )


def build_member_event_service(session: Session) -> MemberEventService:
    """Wire the membership-fact use case writing into the same stream."""
    return MemberEventService(
        unit_of_work=SqlAlchemyChatUnitOfWork(session),
        clock=utc_now,
        id_factory=uuid4,
    )


__all__ = ["build_chat_service", "build_member_event_service"]

"""Post-commit campaigns publisher persisting and broadcasting member joins."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy.orm import Session, sessionmaker

from dunvyr.campaigns.public import CampaignEventPublisher, CampaignMemberSnapshot
from dunvyr.communication.application.wire import event_to_wire
from dunvyr.communication.infrastructure.factory import build_member_event_service
from dunvyr.communication.infrastructure.realtime import RealtimeHub

logger = logging.getLogger(__name__)


class CampaignMemberJoinedPublisher:
    """Adapter implementing campaigns' post-commit event port.

    It writes the membership fact into communication's own stream and only
    then fans it out; failures are logged and never propagated into the already
    committed campaigns transaction.
    """

    def __init__(
        self,
        *,
        session_factory: sessionmaker[Session],
        hub: RealtimeHub,
    ) -> None:
        self._session_factory = session_factory
        self._hub = hub

    def member_joined(
        self,
        campaign_id: UUID,
        member: CampaignMemberSnapshot,
    ) -> None:
        try:
            with self._session_factory() as session:
                result = build_member_event_service(session).record_member_joined(
                    campaign_id,
                    member,
                )
            if result.created:
                self._hub.broadcast(campaign_id, event_to_wire(result.event))
        except Exception:
            logger.warning(
                "Failed to deliver member_joined for campaign %s",
                campaign_id,
                exc_info=True,
            )


def build_campaign_member_joined_publisher(
    session_factory: sessionmaker[Session],
    hub: RealtimeHub,
) -> CampaignEventPublisher:
    return CampaignMemberJoinedPublisher(session_factory=session_factory, hub=hub)


__all__ = ["CampaignMemberJoinedPublisher", "build_campaign_member_joined_publisher"]

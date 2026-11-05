"""Campaigns adapter implementing the public membership reader contract."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.orm import Session

from dunvyr.campaigns.infrastructure.repositories import SqlAlchemyCampaignRepository
from dunvyr.campaigns.public import CampaignMemberSnapshot


class SqlAlchemyCampaignMembershipReader:
    """Read one campaign roster through campaigns' own repository only."""

    def __init__(self, session: Session) -> None:
        self._campaigns = SqlAlchemyCampaignRepository(session)

    def find_member(
        self,
        campaign_id: UUID,
        guest_id: UUID,
    ) -> CampaignMemberSnapshot | None:
        campaign = self._campaigns.get(campaign_id)
        if campaign is None:
            return None
        membership = next(
            (member for member in campaign.members if member.guest_id == guest_id),
            None,
        )
        if membership is None:
            return None
        return CampaignMemberSnapshot(
            guest_id=membership.guest_id,
            nickname=membership.nickname,
            role=membership.role.value,
            joined_at=membership.joined_at,
        )


def build_campaign_membership_reader(session: Session) -> SqlAlchemyCampaignMembershipReader:
    return SqlAlchemyCampaignMembershipReader(session)


__all__ = ["SqlAlchemyCampaignMembershipReader", "build_campaign_membership_reader"]

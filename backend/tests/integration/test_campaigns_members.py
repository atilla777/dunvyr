"""Repository-level checks for the database guards behind invitation joins."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dunvyr.campaigns.application.errors import MembershipInsertConflict
from dunvyr.campaigns.domain.campaign import Campaign
from dunvyr.campaigns.domain.invitation import Invitation
from dunvyr.campaigns.domain.max_seats import MaxSeats
from dunvyr.campaigns.domain.membership import MemberRole, Membership
from dunvyr.campaigns.domain.name import CampaignName
from dunvyr.campaigns.infrastructure.repositories import SqlAlchemyCampaignRepository

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CAMPAIGN_ID = UUID("22222222-2222-4222-8222-222222222222")
ORGANIZER_ID = UUID("11111111-1111-4111-8111-111111111111")
BOB_ID = UUID("33333333-3333-4333-8333-333333333333")
CAROL_ID = UUID("44444444-4444-4444-8444-444444444444")


def build_campaign(*, max_seats: int = 2) -> Campaign:
    return Campaign.create(
        id=CAMPAIGN_ID,
        name=CampaignName.parse("Ночная смена"),
        max_seats=MaxSeats(max_seats),
        organizer_id=ORGANIZER_ID,
        organizer_nickname="Алиса",
        idempotency_key=UUID("55555555-5555-4555-8555-555555555555"),
        invitation=Invitation.issue("raw-invitation-secret"),
        created_at=NOW,
    )


def membership(guest_id: UUID, nickname: str) -> Membership:
    return Membership(
        guest_id=guest_id,
        nickname=nickname,
        role=MemberRole.PLAYER,
        joined_at=NOW,
    )


@pytest.mark.integration
def test_seat_check_and_member_insert_are_one_statement(migrated_engine: Engine) -> None:
    with Session(migrated_engine) as session:
        repository = SqlAlchemyCampaignRepository(session)
        repository.add(build_campaign(max_seats=2))
        session.commit()

        assert repository.add_member_if_seats_available(CAMPAIGN_ID, membership(BOB_ID, "Боб"))
        session.commit()
        assert not repository.add_member_if_seats_available(
            CAMPAIGN_ID, membership(CAROL_ID, "Кэрол")
        )
        session.commit()

        campaign = repository.get(CAMPAIGN_ID)

    assert campaign is not None
    assert [member.nickname for member in campaign.members] == ["Алиса", "Боб"]


@pytest.mark.integration
def test_revoked_invitation_blocks_the_member_insert_guard(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        repository = SqlAlchemyCampaignRepository(session)
        repository.add(build_campaign(max_seats=4).revoke_invitation())
        session.commit()

        assert not repository.add_member_if_seats_available(CAMPAIGN_ID, membership(BOB_ID, "Боб"))
        campaign = repository.get(CAMPAIGN_ID)

    assert campaign is not None
    assert [member.nickname for member in campaign.members] == ["Алиса"]


@pytest.mark.integration
def test_duplicate_nickname_in_one_campaign_is_rejected_by_the_database(
    migrated_engine: Engine,
) -> None:
    with Session(migrated_engine) as session:
        repository = SqlAlchemyCampaignRepository(session)
        repository.add(build_campaign(max_seats=4))
        session.commit()
        assert repository.add_member_if_seats_available(CAMPAIGN_ID, membership(BOB_ID, "Боб"))
        session.commit()

        with pytest.raises(MembershipInsertConflict):
            repository.add_member_if_seats_available(CAMPAIGN_ID, membership(CAROL_ID, "Боб"))
        campaign = repository.get(CAMPAIGN_ID)

    assert campaign is not None
    assert [member.nickname for member in campaign.members] == ["Алиса", "Боб"]

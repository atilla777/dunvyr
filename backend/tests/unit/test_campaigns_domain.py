"""TDD unit tests for the campaigns domain invariants."""

from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from dunvyr.campaigns.domain.campaign import Campaign, InvalidCampaign
from dunvyr.campaigns.domain.invitation import (
    InvalidInvitation,
    Invitation,
    hash_invitation_secret,
)
from dunvyr.campaigns.domain.max_seats import (
    DEFAULT_MAX_SEATS,
    MAX_MAX_SEATS,
    MIN_MAX_SEATS,
    InvalidMaxSeats,
    MaxSeats,
)
from dunvyr.campaigns.domain.membership import InvalidMembership, MemberRole, Membership
from dunvyr.campaigns.domain.name import (
    CAMPAIGN_NAME_MAX_LENGTH,
    CampaignName,
    InvalidCampaignName,
)

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
CAMPAIGN_ID = UUID("33333333-3333-4333-8333-333333333333")
ORGANIZER_ID = UUID("44444444-4444-4444-8444-444444444444")
PLAYER_ID = UUID("55555555-5555-4555-8555-555555555555")
IDEMPOTENCY_KEY = UUID("66666666-6666-4666-8666-666666666666")
SECRET = "raw-invitation-secret"


def build_campaign(*, max_seats: int = DEFAULT_MAX_SEATS) -> Campaign:
    return Campaign.create(
        id=CAMPAIGN_ID,
        name=CampaignName.parse("Ночная смена"),
        max_seats=MaxSeats(max_seats),
        organizer_id=ORGANIZER_ID,
        organizer_nickname="Алиса",
        idempotency_key=IDEMPOTENCY_KEY,
        invitation=Invitation.issue(SECRET),
        created_at=NOW,
    )


@pytest.mark.unit
def test_max_seats_defaults_to_six() -> None:
    assert DEFAULT_MAX_SEATS == 6
    assert MaxSeats.default().value == 6


@pytest.mark.unit
@pytest.mark.parametrize("value", [MIN_MAX_SEATS, 4, MAX_MAX_SEATS])
def test_max_seats_accepts_the_supported_range(value: int) -> None:
    assert MaxSeats(value).value == value


@pytest.mark.unit
@pytest.mark.parametrize("value", [MIN_MAX_SEATS - 1, MAX_MAX_SEATS + 1, 0, -1])
def test_max_seats_rejects_values_outside_the_supported_range(value: int) -> None:
    with pytest.raises(InvalidMaxSeats):
        MaxSeats(value)


@pytest.mark.unit
@pytest.mark.parametrize("value", [True, False, 6.0, "6"])
def test_max_seats_rejects_non_integer_values(value: object) -> None:
    with pytest.raises(InvalidMaxSeats):
        MaxSeats(value)  # type: ignore[arg-type]


@pytest.mark.unit
def test_campaign_name_trims_surrounding_whitespace() -> None:
    assert CampaignName.parse("  Ночная смена  ").value == "Ночная смена"


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["", "   ", "x" * (CAMPAIGN_NAME_MAX_LENGTH + 1), "Alice\nSecond"])
def test_campaign_name_rejects_empty_too_long_or_control_characters(raw: str) -> None:
    with pytest.raises(InvalidCampaignName):
        CampaignName.parse(raw)


@pytest.mark.unit
def test_campaign_name_rejects_non_string_values() -> None:
    with pytest.raises(InvalidCampaignName):
        CampaignName.parse(42)


@pytest.mark.unit
def test_invitation_stores_only_a_sha256_hash_of_the_secret() -> None:
    secret = "raw-invitation-secret"

    invitation = Invitation.issue(secret)

    assert invitation.token_hash == hash_invitation_secret(secret)
    assert invitation.token_hash != secret
    assert len(invitation.token_hash) == 64
    assert "secret" not in {field.name for field in fields(invitation)}


@pytest.mark.unit
def test_fresh_invitation_is_active_and_can_be_revoked_immutably() -> None:
    invitation = Invitation.issue("raw-invitation-secret")

    revoked = invitation.revoke()

    assert invitation.is_active
    assert not revoked.is_active
    assert revoked.token_hash == invitation.token_hash


@pytest.mark.unit
@pytest.mark.parametrize("token_hash", ["", "not-a-sha256-hash", "a" * 63, "A" * 64])
def test_invitation_rejects_invalid_stored_hashes(token_hash: str) -> None:
    with pytest.raises(InvalidInvitation):
        Invitation(token_hash=token_hash)


@pytest.mark.unit
def test_campaign_creation_registers_the_organizer_as_the_only_member() -> None:
    campaign = build_campaign(max_seats=4)

    assert campaign.members == (
        Membership(
            guest_id=ORGANIZER_ID,
            nickname="Алиса",
            role=MemberRole.ORGANIZER,
            joined_at=NOW,
        ),
    )
    assert campaign.seats_taken == 1
    assert campaign.free_seats == 3
    assert campaign.has_free_seats
    assert campaign.has_member(ORGANIZER_ID)
    assert not campaign.has_member(PLAYER_ID)
    assert campaign.is_organizer(ORGANIZER_ID)
    assert campaign.invitation.is_active


@pytest.mark.unit
def test_campaign_requires_exactly_one_organizer_membership() -> None:
    campaign = build_campaign()
    player = Membership(
        guest_id=PLAYER_ID,
        nickname="Боб",
        role=MemberRole.PLAYER,
        joined_at=NOW,
    )

    with pytest.raises(InvalidCampaign):
        replace(campaign, members=())
    with pytest.raises(InvalidCampaign):
        replace(
            campaign,
            members=(campaign.members[0], replace(campaign.members[0], guest_id=PLAYER_ID)),
        )
    with pytest.raises(InvalidCampaign):
        replace(campaign, members=(player,))
    with pytest.raises(InvalidCampaign):
        replace(campaign, organizer_id=PLAYER_ID)


@pytest.mark.unit
def test_campaign_rejects_duplicate_guest_membership() -> None:
    campaign = build_campaign()
    duplicate = replace(campaign.members[0], role=MemberRole.PLAYER)

    with pytest.raises(InvalidCampaign):
        replace(campaign, members=(campaign.members[0], duplicate))


@pytest.mark.unit
def test_campaign_never_has_more_members_than_seats() -> None:
    campaign = build_campaign(max_seats=2)
    player = Membership(
        guest_id=PLAYER_ID,
        nickname="Боб",
        role=MemberRole.PLAYER,
        joined_at=NOW,
    )
    third = Membership(
        guest_id=UUID("77777777-7777-4777-8777-777777777777"),
        nickname="Кэрол",
        role=MemberRole.PLAYER,
        joined_at=NOW,
    )

    full = replace(campaign, members=(campaign.members[0], player))
    assert full.seats_taken == 2
    assert not full.has_free_seats

    with pytest.raises(InvalidCampaign):
        replace(campaign, members=(campaign.members[0], player, third))


@pytest.mark.unit
def test_campaign_requires_timezone_aware_timestamps() -> None:
    campaign = build_campaign()

    with pytest.raises(InvalidCampaign):
        replace(campaign, created_at=datetime(2026, 1, 1, 12, 0))
    with pytest.raises(InvalidMembership):
        replace(
            campaign,
            members=(replace(campaign.members[0], joined_at=datetime(2026, 1, 1, 12, 0)),),
        )


@pytest.mark.unit
def test_campaign_revocation_makes_the_invitation_inactive() -> None:
    campaign = build_campaign()

    revoked = campaign.revoke_invitation()

    assert campaign.invitation.is_active
    assert not revoked.invitation.is_active
    assert revoked.invitation.token_hash == campaign.invitation.token_hash


@pytest.mark.unit
@pytest.mark.parametrize("nickname", ["", "   ", "x" * 33, "Alice\nSecond"])
def test_membership_rejects_invalid_nicknames(nickname: str) -> None:
    with pytest.raises(InvalidMembership):
        Membership(guest_id=PLAYER_ID, nickname=nickname, role=MemberRole.PLAYER, joined_at=NOW)

"""TDD unit tests for the campaigns application use cases with fakes."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from dunvyr.campaigns.application.errors import (
    CampaignAccessDenied,
    CampaignNotFound,
    DuplicateIdempotencyKey,
    InvitationUnavailable,
    MembershipInsertConflict,
    NicknameTaken,
    NoFreeSeats,
)
from dunvyr.campaigns.application.service import CampaignService, CreateCampaign, JoinCampaign
from dunvyr.campaigns.domain.campaign import Campaign
from dunvyr.campaigns.domain.invitation import Invitation, hash_invitation_secret
from dunvyr.campaigns.domain.max_seats import InvalidMaxSeats, MaxSeats
from dunvyr.campaigns.domain.membership import MemberRole, Membership
from dunvyr.campaigns.domain.name import CampaignName, InvalidCampaignName

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
ORGANIZER_ID = UUID("11111111-1111-4111-8111-111111111111")
CAMPAIGN_ID = UUID("22222222-2222-4222-8222-222222222222")
IDEMPOTENCY_KEY = UUID("33333333-3333-4333-8333-333333333333")
OTHER_GUEST_ID = UUID("44444444-4444-4444-8444-444444444444")
RAW_SECRET = "raw-invitation-secret"


class FakeCampaignRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, Campaign] = {}
        self.added: list[Campaign] = []
        self.conflict: Campaign | None = None
        self.member_inserts: list[Membership] = []
        self.member_insert_result = True
        self.failed_insert_campaign: Campaign | None = None
        self.member_conflict: Campaign | None = None
        self.invitation_updates: list[Invitation] = []

    def add(self, campaign: Campaign) -> None:
        if self.conflict is not None:
            self.rows[self.conflict.id] = self.conflict
            self.conflict = None
            raise DuplicateIdempotencyKey
        self.rows[campaign.id] = campaign
        self.added.append(campaign)

    def get(self, campaign_id: UUID) -> Campaign | None:
        return self.rows.get(campaign_id)

    def find_by_organizer_and_idempotency_key(
        self,
        organizer_id: UUID,
        idempotency_key: UUID,
    ) -> Campaign | None:
        return next(
            (
                campaign
                for campaign in self.rows.values()
                if campaign.organizer_id == organizer_id
                and campaign.idempotency_key == idempotency_key
            ),
            None,
        )

    def find_by_invitation_token_hash(self, token_hash: str) -> Campaign | None:
        return next(
            (
                campaign
                for campaign in self.rows.values()
                if campaign.invitation.token_hash == token_hash
            ),
            None,
        )

    def add_member_if_seats_available(
        self,
        campaign_id: UUID,
        membership: Membership,
    ) -> bool:
        if self.member_conflict is not None:
            self.rows[self.member_conflict.id] = self.member_conflict
            self.member_conflict = None
            raise MembershipInsertConflict
        if not self.member_insert_result:
            if self.failed_insert_campaign is not None:
                self.rows[campaign_id] = self.failed_insert_campaign
                self.failed_insert_campaign = None
            return False
        campaign = self.rows[campaign_id]
        self.rows[campaign_id] = replace(campaign, members=(*campaign.members, membership))
        self.member_inserts.append(membership)
        return True

    def update_invitation(self, campaign_id: UUID, invitation: Invitation) -> None:
        campaign = self.rows[campaign_id]
        self.rows[campaign_id] = replace(campaign, invitation=invitation)
        self.invitation_updates.append(invitation)


class FakeUnitOfWork:
    def __init__(self) -> None:
        self.campaigns = FakeCampaignRepository()
        self.commits = 0

    def commit(self) -> None:
        self.commits += 1


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FixedIdFactory:
    def __init__(self, campaign_id: UUID) -> None:
        self.campaign_id = campaign_id
        self.calls = 0

    def __call__(self) -> UUID:
        self.calls += 1
        return self.campaign_id


class FixedInvitationSecretGenerator:
    def __init__(self, secret: str) -> None:
        self.secret = secret
        self.calls = 0

    def generate(self) -> str:
        self.calls += 1
        return self.secret


def build_service(
    *,
    uow: FakeUnitOfWork | None = None,
    secret: str = RAW_SECRET,
) -> tuple[CampaignService, FakeUnitOfWork, FixedInvitationSecretGenerator]:
    resolved_uow = uow or FakeUnitOfWork()
    generator = FixedInvitationSecretGenerator(secret)
    service = CampaignService(
        unit_of_work=resolved_uow,
        invitation_secret_generator=generator,
        clock=FixedClock(NOW),
        id_factory=FixedIdFactory(CAMPAIGN_ID),
    )
    return service, resolved_uow, generator


def command(**overrides: object) -> CreateCampaign:
    values: dict[str, object] = {
        "organizer_id": ORGANIZER_ID,
        "organizer_nickname": "Алиса",
        "name": "Ночная смена",
        "max_seats": 4,
        "idempotency_key": IDEMPOTENCY_KEY,
    }
    values.update(overrides)
    return CreateCampaign(**values)  # type: ignore[arg-type]


@pytest.mark.unit
def test_create_campaign_returns_campaign_and_one_time_secret() -> None:
    service, uow, generator = build_service()

    issued = service.create_campaign(command())

    assert issued.created
    assert issued.campaign.id == CAMPAIGN_ID
    assert issued.campaign.name == "Ночная смена"
    assert issued.campaign.max_seats == 4
    assert issued.campaign.organizer_id == ORGANIZER_ID
    assert issued.campaign.invitation_active
    assert issued.campaign.members[0].guest_id == ORGANIZER_ID
    assert issued.campaign.members[0].nickname == "Алиса"
    assert issued.campaign.members[0].role.value == "organizer"
    assert issued.campaign.created_at == NOW
    assert issued.invitation_secret == RAW_SECRET
    assert generator.calls == 1
    assert uow.commits == 1


@pytest.mark.unit
def test_create_campaign_stores_only_the_secret_hash() -> None:
    service, uow, _generator = build_service()

    service.create_campaign(command())

    stored = uow.campaigns.added[0]
    assert stored.invitation.token_hash == hash_invitation_secret(RAW_SECRET)
    assert stored.invitation.token_hash != RAW_SECRET


@pytest.mark.unit
def test_create_campaign_replays_an_existing_campaign_for_the_same_key() -> None:
    service, uow, generator = build_service()
    first = service.create_campaign(command())

    replay = service.create_campaign(command())

    assert not replay.created
    assert replay.campaign.id == first.campaign.id
    assert replay.invitation_secret is None
    assert generator.calls == 1
    assert uow.commits == 1
    assert len(uow.campaigns.rows) == 1


@pytest.mark.unit
def test_create_campaign_recovers_from_a_database_idempotency_conflict() -> None:
    uow = FakeUnitOfWork()
    service, _uow, _generator = build_service(uow=uow)
    existing = Campaign.create(
        id=CAMPAIGN_ID,
        name=CampaignName.parse("Ночная смена"),
        max_seats=MaxSeats(4),
        organizer_id=ORGANIZER_ID,
        organizer_nickname="Алиса",
        idempotency_key=IDEMPOTENCY_KEY,
        invitation=Invitation.issue(RAW_SECRET),
        created_at=NOW,
    )
    uow.campaigns.conflict = existing

    replay = service.create_campaign(command())

    assert not replay.created
    assert replay.campaign.id == CAMPAIGN_ID
    assert replay.invitation_secret is None


@pytest.mark.unit
@pytest.mark.parametrize("max_seats", [1, 21])
def test_create_campaign_rejects_invalid_seat_limits(max_seats: int) -> None:
    service, uow, generator = build_service()

    with pytest.raises(InvalidMaxSeats):
        service.create_campaign(command(max_seats=max_seats))

    assert uow.commits == 0
    assert generator.calls == 0


@pytest.mark.unit
def test_create_campaign_rejects_invalid_names() -> None:
    service, uow, _generator = build_service()

    with pytest.raises(InvalidCampaignName):
        service.create_campaign(command(name="   "))

    assert uow.commits == 0


@pytest.mark.unit
def test_get_campaign_returns_the_view_for_a_member() -> None:
    service, _uow, _generator = build_service()
    issued = service.create_campaign(command())

    view = service.get_campaign(CAMPAIGN_ID, ORGANIZER_ID)

    assert view == issued.campaign


@pytest.mark.unit
def test_get_campaign_raises_not_found_for_a_missing_campaign() -> None:
    service, _uow, _generator = build_service()

    with pytest.raises(CampaignNotFound):
        service.get_campaign(CAMPAIGN_ID, ORGANIZER_ID)


@pytest.mark.unit
def test_get_campaign_denies_a_guest_who_is_not_a_member() -> None:
    service, _uow, _generator = build_service()
    service.create_campaign(command())

    with pytest.raises(CampaignAccessDenied):
        service.get_campaign(CAMPAIGN_ID, OTHER_GUEST_ID)


def join_command(**overrides: object) -> JoinCampaign:
    values: dict[str, object] = {
        "secret": RAW_SECRET,
        "guest_id": OTHER_GUEST_ID,
        "guest_nickname": "Боб",
    }
    values.update(overrides)
    return JoinCampaign(**values)  # type: ignore[arg-type]


@pytest.mark.unit
def test_join_campaign_adds_a_player_and_returns_its_membership() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command(max_seats=4))

    joined = service.join_campaign(join_command())

    assert joined.joined
    assert joined.campaign.id == CAMPAIGN_ID
    assert [member.nickname for member in joined.campaign.members] == ["Алиса", "Боб"]
    assert joined.campaign.members[-1].role is MemberRole.PLAYER
    assert joined.campaign.members[-1].joined_at == NOW
    assert [
        (member.guest_id, member.nickname, member.role) for member in uow.campaigns.member_inserts
    ] == [(OTHER_GUEST_ID, "Боб", MemberRole.PLAYER)]
    assert uow.commits == 2


@pytest.mark.unit
def test_join_campaign_replays_the_same_guest_without_a_new_seat_or_commit() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command(max_seats=4))
    first = service.join_campaign(join_command())

    replay = service.join_campaign(join_command())

    assert first.joined
    assert not replay.joined
    assert replay.campaign.id == first.campaign.id
    assert [member.nickname for member in replay.campaign.members] == ["Алиса", "Боб"]
    assert len(uow.campaigns.member_inserts) == 1
    assert uow.commits == 2


@pytest.mark.unit
def test_join_campaign_rejects_an_unknown_secret() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command())

    with pytest.raises(InvitationUnavailable):
        service.join_campaign(join_command(secret="unknown-secret"))

    assert uow.campaigns.member_inserts == []
    assert uow.commits == 1


@pytest.mark.unit
def test_join_campaign_rejects_a_revoked_invitation() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command())
    service.revoke_invitation(CAMPAIGN_ID, ORGANIZER_ID)

    with pytest.raises(InvitationUnavailable):
        service.join_campaign(join_command())

    assert uow.campaigns.member_inserts == []


@pytest.mark.unit
def test_join_campaign_rejects_a_campaign_without_free_seats() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command(max_seats=2))
    service.join_campaign(join_command())
    third_guest_id = UUID("55555555-5555-4555-8555-555555555555")

    with pytest.raises(NoFreeSeats):
        service.join_campaign(join_command(guest_id=third_guest_id, guest_nickname="Кэрол"))

    assert len(uow.campaigns.member_inserts) == 1


@pytest.mark.unit
def test_join_campaign_rejects_a_taken_nickname() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command())

    with pytest.raises(NicknameTaken):
        service.join_campaign(join_command(guest_nickname="Алиса"))

    assert uow.campaigns.member_inserts == []


@pytest.mark.unit
def test_join_campaign_reports_a_seat_race_lost_at_the_database() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command())
    uow.campaigns.member_insert_result = False

    with pytest.raises(NoFreeSeats):
        service.join_campaign(join_command())

    assert uow.campaigns.member_inserts == []
    assert uow.commits == 1


@pytest.mark.unit
def test_join_campaign_reports_a_revoke_race_lost_at_the_database() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command())
    stale = uow.campaigns.rows[CAMPAIGN_ID]
    uow.campaigns.member_insert_result = False
    uow.campaigns.failed_insert_campaign = stale.revoke_invitation()

    with pytest.raises(InvitationUnavailable):
        service.join_campaign(join_command())

    assert uow.campaigns.member_inserts == []
    assert uow.commits == 1


@pytest.mark.unit
def test_join_campaign_replays_when_the_insert_races_with_the_same_guest() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command(max_seats=4))
    stale = uow.campaigns.rows[CAMPAIGN_ID]
    winner = replace(
        stale,
        members=(
            *stale.members,
            Membership(
                guest_id=OTHER_GUEST_ID,
                nickname="Боб",
                role=MemberRole.PLAYER,
                joined_at=NOW,
            ),
        ),
    )
    uow.campaigns.member_conflict = winner

    joined = service.join_campaign(join_command())

    assert not joined.joined
    assert [member.nickname for member in joined.campaign.members] == ["Алиса", "Боб"]
    assert uow.campaigns.member_inserts == []
    assert uow.commits == 1


@pytest.mark.unit
def test_join_campaign_reports_a_nickname_race_lost_at_the_database() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command(max_seats=4))
    stale = uow.campaigns.rows[CAMPAIGN_ID]
    winner = replace(
        stale,
        members=(
            *stale.members,
            Membership(
                guest_id=UUID("55555555-5555-4555-8555-555555555555"),
                nickname="Боб",
                role=MemberRole.PLAYER,
                joined_at=NOW,
            ),
        ),
    )
    uow.campaigns.member_conflict = winner

    with pytest.raises(NicknameTaken):
        service.join_campaign(join_command())

    assert uow.campaigns.member_inserts == []


@pytest.mark.unit
def test_revoke_invitation_deactivates_it_for_the_organizer() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command())

    view = service.revoke_invitation(CAMPAIGN_ID, ORGANIZER_ID)

    assert not view.invitation_active
    assert not uow.campaigns.invitation_updates[0].is_active
    assert uow.commits == 2


@pytest.mark.unit
def test_revoke_invitation_is_idempotent_after_the_first_success() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command())
    first = service.revoke_invitation(CAMPAIGN_ID, ORGANIZER_ID)

    replay = service.revoke_invitation(CAMPAIGN_ID, ORGANIZER_ID)

    assert not first.invitation_active
    assert not replay.invitation_active
    assert len(uow.campaigns.invitation_updates) == 1
    assert uow.commits == 2


@pytest.mark.unit
def test_revoke_invitation_is_forbidden_for_non_organizers() -> None:
    service, uow, _generator = build_service()
    service.create_campaign(command(max_seats=4))
    service.join_campaign(join_command())

    with pytest.raises(CampaignAccessDenied):
        service.revoke_invitation(CAMPAIGN_ID, OTHER_GUEST_ID)

    assert uow.campaigns.invitation_updates == []
    assert uow.commits == 2


@pytest.mark.unit
def test_revoke_invitation_is_not_found_for_a_missing_campaign() -> None:
    service, _uow, _generator = build_service()

    with pytest.raises(CampaignNotFound):
        service.revoke_invitation(CAMPAIGN_ID, ORGANIZER_ID)

"""TDD unit tests for the campaigns application use cases with fakes."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from dunvyr.campaigns.application.errors import (
    CampaignAccessDenied,
    CampaignNotFound,
    DuplicateIdempotencyKey,
)
from dunvyr.campaigns.application.service import CampaignService, CreateCampaign
from dunvyr.campaigns.domain.campaign import Campaign
from dunvyr.campaigns.domain.invitation import Invitation, hash_invitation_secret
from dunvyr.campaigns.domain.max_seats import InvalidMaxSeats, MaxSeats
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

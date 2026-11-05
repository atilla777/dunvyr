"""Skeleton campaigns application service for the TDD red step."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from dunvyr.campaigns.application.errors import (
    CampaignAccessDenied,
    CampaignNotFound,
    DuplicateIdempotencyKey,
    InvitationUnavailable,
    MembershipInsertConflict,
    NicknameTaken,
    NoFreeSeats,
)
from dunvyr.campaigns.application.ports import (
    Clock,
    IdFactory,
    InvitationSecretGenerator,
    UnitOfWork,
)
from dunvyr.campaigns.domain.campaign import (
    Campaign,
    CampaignFull,
    InvitationInactive,
)
from dunvyr.campaigns.domain.campaign import (
    NicknameTaken as DomainNicknameTaken,
)
from dunvyr.campaigns.domain.invitation import Invitation, hash_invitation_secret
from dunvyr.campaigns.domain.max_seats import MaxSeats
from dunvyr.campaigns.domain.membership import MemberRole
from dunvyr.campaigns.domain.name import CampaignName


@dataclass(frozen=True, slots=True)
class CreateCampaign:
    organizer_id: UUID
    organizer_nickname: str
    name: str
    max_seats: int
    idempotency_key: UUID


@dataclass(frozen=True, slots=True)
class JoinCampaign:
    secret: str
    guest_id: UUID
    guest_nickname: str


@dataclass(frozen=True, slots=True)
class CampaignMemberView:
    guest_id: UUID
    nickname: str
    role: MemberRole
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class CampaignView:
    id: UUID
    name: str
    max_seats: int
    organizer_id: UUID
    invitation_active: bool
    members: tuple[CampaignMemberView, ...]
    created_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedCampaign:
    campaign: CampaignView
    invitation_secret: str | None
    created: bool


@dataclass(frozen=True, slots=True)
class JoinedCampaign:
    campaign: CampaignView
    joined: bool


def _view(campaign: Campaign) -> CampaignView:
    return CampaignView(
        id=campaign.id,
        name=campaign.name.value,
        max_seats=campaign.max_seats.value,
        organizer_id=campaign.organizer_id,
        invitation_active=campaign.invitation.is_active,
        members=tuple(
            CampaignMemberView(
                guest_id=member.guest_id,
                nickname=member.nickname,
                role=member.role,
                joined_at=member.joined_at,
            )
            for member in campaign.members
        ),
        created_at=campaign.created_at,
    )


class CampaignService:
    """Application service implementing the organizer campaign slice."""

    def __init__(
        self,
        *,
        unit_of_work: UnitOfWork,
        invitation_secret_generator: InvitationSecretGenerator,
        clock: Clock,
        id_factory: IdFactory,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._invitation_secret_generator = invitation_secret_generator
        self._clock = clock
        self._id_factory = id_factory

    def create_campaign(self, command: CreateCampaign) -> IssuedCampaign:
        existing = self._unit_of_work.campaigns.find_by_organizer_and_idempotency_key(
            command.organizer_id,
            command.idempotency_key,
        )
        if existing is not None:
            return IssuedCampaign(campaign=_view(existing), invitation_secret=None, created=False)

        name = CampaignName.parse(command.name)
        max_seats = MaxSeats(command.max_seats)
        now = self._clock()
        secret = self._invitation_secret_generator.generate()
        campaign = Campaign.create(
            id=self._id_factory(),
            name=name,
            max_seats=max_seats,
            organizer_id=command.organizer_id,
            organizer_nickname=command.organizer_nickname,
            idempotency_key=command.idempotency_key,
            invitation=Invitation.issue(secret),
            created_at=now,
        )
        try:
            self._unit_of_work.campaigns.add(campaign)
            self._unit_of_work.commit()
        except DuplicateIdempotencyKey:
            # A concurrent request won the database uniqueness race; the
            # winner already owns this key, so replay its campaign.
            existing = self._unit_of_work.campaigns.find_by_organizer_and_idempotency_key(
                command.organizer_id,
                command.idempotency_key,
            )
            if existing is None:
                raise
            return IssuedCampaign(
                campaign=_view(existing),
                invitation_secret=None,
                created=False,
            )
        return IssuedCampaign(campaign=_view(campaign), invitation_secret=secret, created=True)

    def get_campaign(self, campaign_id: UUID, viewer_id: UUID) -> CampaignView:
        campaign = self._unit_of_work.campaigns.get(campaign_id)
        if campaign is None:
            raise CampaignNotFound
        if not campaign.has_member(viewer_id):
            raise CampaignAccessDenied
        return _view(campaign)

    def join_campaign(self, command: JoinCampaign) -> JoinedCampaign:
        """Join by invitation secret; a repeated join replays without a new seat."""
        token_hash = hash_invitation_secret(command.secret)
        campaign = self._unit_of_work.campaigns.find_by_invitation_token_hash(token_hash)
        if campaign is None or not campaign.invitation.is_active:
            raise InvitationUnavailable
        if campaign.has_member(command.guest_id):
            return JoinedCampaign(campaign=_view(campaign), joined=False)

        try:
            joined = campaign.join(command.guest_id, command.guest_nickname, self._clock())
        except InvitationInactive as error:
            raise InvitationUnavailable from error
        except CampaignFull as error:
            raise NoFreeSeats from error
        except DomainNicknameTaken as error:
            raise NicknameTaken from error

        membership = joined.members[-1]
        try:
            inserted = self._unit_of_work.campaigns.add_member_if_seats_available(
                campaign.id,
                membership,
            )
            if not inserted:
                # The insert lost a seat or revoke race; the read snapshot was
                # reset by the repository, so re-read before explaining why.
                current = self._unit_of_work.campaigns.get(campaign.id)
                if current is None:
                    raise InvitationUnavailable
                if current.has_member(command.guest_id):
                    return JoinedCampaign(campaign=_view(current), joined=False)
                if not current.invitation.is_active:
                    raise InvitationUnavailable
                raise NoFreeSeats
            self._unit_of_work.commit()
        except MembershipInsertConflict:
            # A concurrent row made the member insert fail: either this guest
            # already joined (replay) or another member owns the nickname.
            current = self._unit_of_work.campaigns.get(campaign.id)
            if current is not None and current.has_member(command.guest_id):
                return JoinedCampaign(campaign=_view(current), joined=False)
            if current is not None and any(
                member.nickname == command.guest_nickname for member in current.members
            ):
                raise NicknameTaken from None
            raise
        return JoinedCampaign(campaign=_view(joined), joined=True)

    def revoke_invitation(self, campaign_id: UUID, actor_id: UUID) -> CampaignView:
        """Revoke the campaign invitation; only its organizer may do so."""
        campaign = self._unit_of_work.campaigns.get(campaign_id)
        if campaign is None:
            raise CampaignNotFound
        if not campaign.is_organizer(actor_id):
            raise CampaignAccessDenied
        if not campaign.invitation.is_active:
            return _view(campaign)

        revoked = campaign.revoke_invitation()
        self._unit_of_work.campaigns.update_invitation(campaign_id, revoked.invitation)
        self._unit_of_work.commit()
        return _view(revoked)

"""Campaign aggregate: one organizer, bounded seats and one revocable invite."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from dunvyr.campaigns.domain.invitation import Invitation
from dunvyr.campaigns.domain.max_seats import MaxSeats
from dunvyr.campaigns.domain.membership import MemberRole, Membership
from dunvyr.campaigns.domain.name import CampaignName
from dunvyr.campaigns.domain.time import require_aware


class InvalidCampaign(ValueError):
    """Raised when a campaign aggregate violates its invariants."""


@dataclass(frozen=True, slots=True)
class Campaign:
    """A campaign group with exactly one organizer and one invitation.

    The organizer is a regular member who also occupies a seat; the number of
    members can never exceed ``max_seats``.
    """

    id: UUID
    name: CampaignName
    max_seats: MaxSeats
    organizer_id: UUID
    idempotency_key: UUID
    invitation: Invitation
    members: tuple[Membership, ...]
    created_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            raise InvalidCampaign("Campaign id must be a UUID")
        if not isinstance(self.name, CampaignName):
            raise InvalidCampaign("Campaign name must be a CampaignName")
        if not isinstance(self.max_seats, MaxSeats):
            raise InvalidCampaign("Campaign max_seats must be a MaxSeats")
        if not isinstance(self.organizer_id, UUID):
            raise InvalidCampaign("Campaign organizer_id must be a UUID")
        if not isinstance(self.idempotency_key, UUID):
            raise InvalidCampaign("Campaign idempotency_key must be a UUID")
        if not isinstance(self.invitation, Invitation):
            raise InvalidCampaign("Campaign invitation must be an Invitation")
        if not isinstance(self.members, tuple):
            raise InvalidCampaign("Campaign members must be a tuple")
        if not all(isinstance(member, Membership) for member in self.members):
            raise InvalidCampaign("Campaign members must be Membership values")
        try:
            require_aware(self.created_at, "created_at")
        except ValueError as error:
            raise InvalidCampaign(str(error)) from error

        organizers = [member for member in self.members if member.role is MemberRole.ORGANIZER]
        if len(organizers) != 1:
            raise InvalidCampaign("Campaign must have exactly one organizer")
        if organizers[0].guest_id != self.organizer_id:
            raise InvalidCampaign("Organizer membership must match organizer_id")

        guest_ids = [member.guest_id for member in self.members]
        if len(set(guest_ids)) != len(guest_ids):
            raise InvalidCampaign("Campaign members must be unique")
        if len(self.members) > self.max_seats.value:
            raise InvalidCampaign("Campaign cannot have more members than seats")

    @classmethod
    def create(
        cls,
        *,
        id: UUID,
        name: CampaignName,
        max_seats: MaxSeats,
        organizer_id: UUID,
        organizer_nickname: str,
        idempotency_key: UUID,
        invitation: Invitation,
        created_at: datetime,
    ) -> Campaign:
        """Create a campaign whose only member is its organizer."""
        return cls(
            id=id,
            name=name,
            max_seats=max_seats,
            organizer_id=organizer_id,
            idempotency_key=idempotency_key,
            invitation=invitation,
            members=(
                Membership(
                    guest_id=organizer_id,
                    nickname=organizer_nickname,
                    role=MemberRole.ORGANIZER,
                    joined_at=created_at,
                ),
            ),
            created_at=created_at,
        )

    @property
    def seats_taken(self) -> int:
        return len(self.members)

    @property
    def free_seats(self) -> int:
        return self.max_seats.value - self.seats_taken

    @property
    def has_free_seats(self) -> bool:
        return self.free_seats > 0

    def has_member(self, guest_id: UUID) -> bool:
        return any(member.guest_id == guest_id for member in self.members)

    def is_organizer(self, guest_id: UUID) -> bool:
        return self.organizer_id == guest_id

    def revoke_invitation(self) -> Campaign:
        """Return a copy with an inactive invitation; the original is unchanged."""
        return replace(self, invitation=self.invitation.revoke())

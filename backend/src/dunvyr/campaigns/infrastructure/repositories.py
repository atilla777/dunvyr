"""SQLAlchemy Core repositories translating between rows and campaign objects."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dunvyr.campaigns.application.errors import DuplicateIdempotencyKey
from dunvyr.campaigns.domain.campaign import Campaign
from dunvyr.campaigns.domain.invitation import Invitation
from dunvyr.campaigns.domain.max_seats import MaxSeats
from dunvyr.campaigns.domain.membership import MemberRole, Membership
from dunvyr.campaigns.domain.name import CampaignName
from dunvyr.campaigns.infrastructure import tables


def _to_text(value: datetime) -> str:
    return value.isoformat()


def _from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqlAlchemyCampaignRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, campaign: Campaign) -> None:
        try:
            self._session.execute(
                tables.campaigns.insert().values(
                    id=str(campaign.id),
                    name=campaign.name.value,
                    max_seats=campaign.max_seats.value,
                    organizer_id=str(campaign.organizer_id),
                    idempotency_key=str(campaign.idempotency_key),
                    invitation_token_hash=campaign.invitation.token_hash,
                    invitation_revoked=campaign.invitation.revoked,
                    created_at=_to_text(campaign.created_at),
                )
            )
            self._session.execute(
                tables.members.insert(),
                [
                    {
                        "campaign_id": str(campaign.id),
                        "guest_id": str(member.guest_id),
                        "nickname": member.nickname,
                        "role": member.role.value,
                        "joined_at": _to_text(member.joined_at),
                    }
                    for member in campaign.members
                ],
            )
        except IntegrityError as error:
            self._session.rollback()
            raise DuplicateIdempotencyKey from error

    def get(self, campaign_id: UUID) -> Campaign | None:
        row = (
            self._session.execute(
                select(tables.campaigns).where(tables.campaigns.c.id == str(campaign_id))
            )
            .mappings()
            .first()
        )
        if row is None:
            return None

        member_rows = (
            self._session.execute(
                select(tables.members)
                .where(tables.members.c.campaign_id == str(campaign_id))
                .order_by(
                    case((tables.members.c.role == MemberRole.ORGANIZER.value, 0), else_=1),
                    tables.members.c.joined_at,
                    tables.members.c.guest_id,
                )
            )
            .mappings()
            .all()
        )
        return _to_campaign(row, member_rows)

    def find_by_organizer_and_idempotency_key(
        self,
        organizer_id: UUID,
        idempotency_key: UUID,
    ) -> Campaign | None:
        campaign_id = self._session.execute(
            select(tables.campaigns.c.id).where(
                tables.campaigns.c.organizer_id == str(organizer_id),
                tables.campaigns.c.idempotency_key == str(idempotency_key),
            )
        ).scalar_one_or_none()
        if campaign_id is None:
            return None
        return self.get(UUID(campaign_id))


def _to_campaign(row: RowMapping, member_rows: Sequence[RowMapping]) -> Campaign:
    return Campaign(
        id=UUID(row["id"]),
        name=CampaignName.parse(row["name"]),
        max_seats=MaxSeats(row["max_seats"]),
        organizer_id=UUID(row["organizer_id"]),
        idempotency_key=UUID(row["idempotency_key"]),
        invitation=Invitation(
            token_hash=row["invitation_token_hash"],
            revoked=bool(row["invitation_revoked"]),
        ),
        members=tuple(
            Membership(
                guest_id=UUID(member["guest_id"]),
                nickname=member["nickname"],
                role=MemberRole(member["role"]),
                joined_at=_from_text(member["joined_at"]),
            )
            for member in member_rows
        ),
        created_at=_from_text(row["created_at"]),
    )


class SqlAlchemyUnitOfWork:
    """One short transaction for a single campaigns use case."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._campaigns = SqlAlchemyCampaignRepository(session)

    @property
    def campaigns(self) -> SqlAlchemyCampaignRepository:
        return self._campaigns

    def commit(self) -> None:
        self._session.commit()

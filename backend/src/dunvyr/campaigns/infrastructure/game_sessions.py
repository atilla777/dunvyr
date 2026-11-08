"""Campaigns-owned session persistence and transactional boundary."""

import json
from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from dunvyr.campaigns.application.errors import CampaignAccessDenied, CampaignNotFound
from dunvyr.campaigns.application.game_sessions import SessionCommand, SessionConflict
from dunvyr.campaigns.infrastructure import tables as t
from dunvyr.campaigns.public import GameSessionSnapshot, GameSessionState


def state_data(state: GameSessionState) -> dict[str, object]:
    session = state.session
    return {
        "revision": state.revision,
        "session": None
        if session is None
        else {
            "id": str(session.id),
            "status": session.status,
            "started_at": session.started_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        },
    }


def decode_state(value: str) -> GameSessionState:
    data = json.loads(value)
    session = data["session"]
    return GameSessionState(
        data["revision"],
        None
        if session is None
        else GameSessionSnapshot(
            UUID(session["id"]),
            session["status"],
            datetime.fromisoformat(session["started_at"]),
            datetime.fromisoformat(session["ended_at"]) if session["ended_at"] else None,
        ),
    )


class SqlGameSessionUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock(self, campaign_id: UUID) -> None:
        # A real SQLite write obtains its writer lock even for an unchanged
        # value. It is held until the owning UoW commits/rolls back.
        self.session.execute(
            update(t.session_state)
            .where(t.session_state.c.campaign_id == str(campaign_id))
            .values(revision=t.session_state.c.revision)
        )

    def authorize(self, campaign_id: UUID, actor_id: UUID, *, organizer: bool) -> None:
        owner = self.session.execute(
            select(t.campaigns.c.organizer_id).where(t.campaigns.c.id == str(campaign_id))
        ).scalar_one_or_none()
        if owner is None:
            raise CampaignNotFound
        member = self.session.execute(
            select(t.members.c.guest_id).where(
                t.members.c.campaign_id == str(campaign_id), t.members.c.guest_id == str(actor_id)
            )
        ).scalar_one_or_none()
        if member is None or (organizer and owner != str(actor_id)):
            raise CampaignAccessDenied

    def read(self, campaign_id: UUID) -> GameSessionState:
        row = (
            self.session.execute(
                select(t.session_state.c.revision, t.game_sessions)
                .select_from(
                    t.session_state.outerjoin(
                        t.game_sessions, t.game_sessions.c.id == t.session_state.c.session_id
                    )
                )
                .where(t.session_state.c.campaign_id == str(campaign_id))
            )
            .mappings()
            .one()
        )
        if row["id"] is None:
            return GameSessionState(row["revision"], None)
        return GameSessionState(
            row["revision"],
            GameSessionSnapshot(
                UUID(row["id"]),
                row["status"],
                datetime.fromisoformat(row["started_at"]),
                datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            ),
        )

    def receipt(self, command: SessionCommand) -> tuple[str, GameSessionState] | None:
        row = (
            self.session.execute(
                select(t.session_receipts).where(
                    t.session_receipts.c.campaign_id == str(command.campaign_id),
                    t.session_receipts.c.actor_id == str(command.actor_id),
                    t.session_receipts.c.key == str(command.key),
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else (row["payload"], decode_state(row["response"]))

    def save(self, command: SessionCommand, state: GameSessionState) -> None:
        assert state.session is not None
        session = state.session
        values = dict(
            status=session.status,
            ended_at=session.ended_at.isoformat() if session.ended_at else None,
        )
        if command.action == "start":
            self.session.execute(
                t.game_sessions.insert().values(
                    id=str(session.id),
                    campaign_id=str(command.campaign_id),
                    started_at=session.started_at.isoformat(),
                    **values,
                )
            )
        else:
            self.session.execute(
                update(t.game_sessions)
                .where(
                    t.game_sessions.c.id == str(session.id),
                    t.game_sessions.c.campaign_id == str(command.campaign_id),
                )
                .values(**values)
            )
        result = self.session.execute(
            update(t.session_state)
            .where(
                t.session_state.c.campaign_id == str(command.campaign_id),
                t.session_state.c.revision == command.expected_revision,
            )
            .values(revision=state.revision, session_id=str(session.id))
        )
        if getattr(result, "rowcount", 0) != 1:
            raise SessionConflict("stale_state")
        self.session.execute(
            t.session_receipts.insert().values(
                campaign_id=str(command.campaign_id),
                actor_id=str(command.actor_id),
                key=str(command.key),
                payload=command.payload(),
                response=json.dumps(state_data(state)),
            )
        )

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

"""SQLAlchemy Core repository for the communication event stream."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dunvyr.communication.application.errors import EventAppendConflict
from dunvyr.communication.domain.events import (
    ChatEvent,
    ChatMember,
    GameSessionChangedEvent,
    MemberJoinedEvent,
    MessageEvent,
)
from dunvyr.communication.domain.message import Message
from dunvyr.communication.infrastructure import tables

MESSAGE_KIND = "message"
MEMBER_JOINED_KIND = "member_joined"


def _to_text(value: datetime) -> str:
    return value.isoformat()


def _from_text(value: str) -> datetime:
    return datetime.fromisoformat(value)


class SqlAlchemyChatEventRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_message_by_client_id(
        self,
        campaign_id: UUID,
        client_message_id: UUID,
    ) -> MessageEvent | None:
        row = (
            self._session.execute(
                select(tables.communication_events).where(
                    tables.communication_events.c.campaign_id == str(campaign_id),
                    tables.communication_events.c.kind == MESSAGE_KIND,
                    tables.communication_events.c.client_message_id == str(client_message_id),
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _to_message_event(row)

    def find_member_joined(
        self,
        campaign_id: UUID,
        guest_id: UUID,
    ) -> MemberJoinedEvent | None:
        row = (
            self._session.execute(
                select(tables.communication_events).where(
                    tables.communication_events.c.campaign_id == str(campaign_id),
                    tables.communication_events.c.kind == MEMBER_JOINED_KIND,
                    tables.communication_events.c.member_guest_id == str(guest_id),
                )
            )
            .mappings()
            .first()
        )
        return None if row is None else _to_member_event(row)

    def next_sequence(self, campaign_id: UUID) -> int:
        highest = self._session.execute(
            select(func.coalesce(func.max(tables.communication_events.c.sequence), 0)).where(
                tables.communication_events.c.campaign_id == str(campaign_id)
            )
        ).scalar_one()
        return int(highest) + 1

    def append(self, event: ChatEvent) -> None:
        values: dict[str, Any] = {
            "campaign_id": str(event.campaign_id),
            "sequence": event.sequence,
            "event_id": str(event.event_id),
            "occurred_at": _to_text(event.occurred_at),
        }
        if isinstance(event, MessageEvent):
            values.update(
                kind=MESSAGE_KIND,
                message_id=str(event.message.id),
                author_id=str(event.message.author_id),
                author_nickname=event.message.author_nickname,
                client_message_id=str(event.message.client_message_id),
                content=event.message.content,
            )
        elif isinstance(event, MemberJoinedEvent):
            values.update(
                kind=MEMBER_JOINED_KIND,
                member_guest_id=str(event.member.guest_id),
                member_nickname=event.member.nickname,
                member_role=event.member.role,
                member_joined_at=_to_text(event.member.joined_at),
            )
        else:
            from dunvyr.communication.application.wire import event_to_wire

            values.update(
                kind="game_session_changed",
                game_session_revision=event.revision,
                game_session_state=json.dumps(event_to_wire(event)["game_session_state"]),
            )
        try:
            self._session.execute(tables.communication_events.insert().values(**values))
        except IntegrityError as error:
            self._session.rollback()
            raise EventAppendConflict from error

    def list_events(
        self,
        campaign_id: UUID,
        *,
        after_sequence: int | None,
        limit: int,
    ) -> list[ChatEvent]:
        statement = select(tables.communication_events).where(
            tables.communication_events.c.campaign_id == str(campaign_id)
        )
        if after_sequence is None:
            # Initial snapshot: the newest slice, returned in ascending order.
            rows = (
                self._session.execute(
                    statement.order_by(tables.communication_events.c.sequence.desc()).limit(limit)
                )
                .mappings()
                .all()
            )
            rows = list(reversed(rows))
        else:
            rows = (
                self._session.execute(
                    statement.where(
                        tables.communication_events.c.sequence > after_sequence
                    ).order_by(tables.communication_events.c.sequence)
                )
                .mappings()
                .all()
            )
        return [_to_event(row) for row in rows]

    def last_sequence(self, campaign_id: UUID) -> int:
        value = self._session.execute(
            select(func.coalesce(func.max(tables.communication_events.c.sequence), 0)).where(
                tables.communication_events.c.campaign_id == str(campaign_id)
            )
        ).scalar_one()
        return int(value)


def _to_event(row: RowMapping) -> ChatEvent:
    if row["kind"] == "game_session_changed":
        state = json.loads(row["game_session_state"])
        session = state["session"]
        return GameSessionChangedEvent(
            event_id=UUID(row["event_id"]),
            campaign_id=UUID(row["campaign_id"]),
            sequence=row["sequence"],
            occurred_at=_from_text(row["occurred_at"]),
            revision=state["revision"],
            session_id=UUID(session["id"]),
            status=session["status"],
            started_at=_from_text(session["started_at"]),
            ended_at=_from_text(session["ended_at"]) if session["ended_at"] else None,
        )
    if row["kind"] == MESSAGE_KIND:
        return _to_message_event(row)
    return _to_member_event(row)


def _to_message_event(row: RowMapping) -> MessageEvent:
    message = Message(
        id=UUID(cast(str, row["message_id"])),
        campaign_id=UUID(cast(str, row["campaign_id"])),
        author_id=UUID(cast(str, row["author_id"])),
        author_nickname=cast(str, row["author_nickname"]),
        client_message_id=UUID(cast(str, row["client_message_id"])),
        content=cast(str, row["content"]),
        created_at=_from_text(cast(str, row["occurred_at"])),
    )
    return MessageEvent(
        event_id=UUID(cast(str, row["event_id"])),
        campaign_id=message.campaign_id,
        sequence=cast(int, row["sequence"]),
        occurred_at=_from_text(cast(str, row["occurred_at"])),
        message=message,
    )


def _to_member_event(row: RowMapping) -> MemberJoinedEvent:
    return MemberJoinedEvent(
        event_id=UUID(cast(str, row["event_id"])),
        campaign_id=UUID(cast(str, row["campaign_id"])),
        sequence=cast(int, row["sequence"]),
        occurred_at=_from_text(cast(str, row["occurred_at"])),
        member=ChatMember(
            guest_id=UUID(cast(str, row["member_guest_id"])),
            nickname=cast(str, row["member_nickname"]),
            role=cast(str, row["member_role"]),
            joined_at=_from_text(cast(str, row["member_joined_at"])),
        ),
    )


class SqlAlchemyChatUnitOfWork:
    """One short transaction for a single communication use case."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._events = SqlAlchemyChatEventRepository(session)

    @property
    def events(self) -> SqlAlchemyChatEventRepository:
        return self._events

    def commit(self) -> None:
        self._session.commit()


__all__ = ["SqlAlchemyChatEventRepository", "SqlAlchemyChatUnitOfWork"]

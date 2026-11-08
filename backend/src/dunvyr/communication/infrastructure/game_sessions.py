"""Explicit campaigns transaction participant, and separate postcommit delivery."""

import json
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from dunvyr.campaigns.public import GameSessionChanged
from dunvyr.communication.application.wire import event_to_wire
from dunvyr.communication.domain.events import GameSessionChangedEvent
from dunvyr.communication.infrastructure.realtime import RealtimeHub
from dunvyr.communication.infrastructure.repositories import (
    SqlAlchemyChatEventRepository,
    _to_event,
)
from dunvyr.communication.infrastructure.tables import communication_events


class GameSessionEventStager:
    """Only inserts communication rows using the injected transaction.

    Deliberately does not use repository.append: that legacy method can roll
    back on conflict, whereas only the campaigns UoW may end this transaction.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def stage(self, fact: GameSessionChanged) -> UUID:
        snapshot = fact.state.session
        assert snapshot is not None
        event = GameSessionChangedEvent(
            event_id=uuid4(),
            campaign_id=fact.campaign_id,
            sequence=SqlAlchemyChatEventRepository(self.session).next_sequence(fact.campaign_id),
            occurred_at=fact.occurred_at,
            revision=fact.state.revision,
            session_id=snapshot.id,
            status=snapshot.status,
            started_at=snapshot.started_at,
            ended_at=snapshot.ended_at,
        )
        self.session.execute(
            communication_events.insert().values(
                campaign_id=str(fact.campaign_id),
                sequence=event.sequence,
                event_id=str(event.event_id),
                kind="game_session_changed",
                occurred_at=fact.occurred_at.isoformat(),
                game_session_revision=fact.state.revision,
                game_session_state=json.dumps(event_to_wire(event)["game_session_state"]),
            )
        )
        return event.event_id


class GameSessionNotifier:
    def __init__(self, sessions: sessionmaker[Session], hub: RealtimeHub) -> None:
        self.sessions, self.hub = sessions, hub

    def notify(self, campaign_id: UUID, event_id: UUID) -> None:
        with self.sessions() as session:
            row = (
                session.execute(
                    select(communication_events).where(
                        communication_events.c.campaign_id == str(campaign_id),
                        communication_events.c.event_id == str(event_id),
                    )
                )
                .mappings()
                .one()
            )
            payload = event_to_wire(_to_event(row))
        self.hub.broadcast(campaign_id, payload)

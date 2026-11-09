"""Atomic durable queue fact in the shared stream; delivery remains postcommit."""

import json
from dataclasses import asdict
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dunvyr.communication.infrastructure.repositories import SqlAlchemyChatEventRepository
from dunvyr.communication.infrastructure.tables import communication_events
from dunvyr.gameplay.public import QueueState


class QueueEventStager:
    def __init__(self, session: Session) -> None:
        self.session = session

    def stage(self, campaign_id: UUID, state: QueueState, now: datetime) -> UUID:
        event_id = uuid4()
        self.session.execute(
            communication_events.insert().values(
                campaign_id=str(campaign_id),
                event_id=str(event_id),
                kind="queue_changed",
                sequence=SqlAlchemyChatEventRepository(self.session).next_sequence(campaign_id),
                occurred_at=now.isoformat(),
                queue_version=state.version,
                queue_state=json.dumps(asdict(state)),
            )
        )
        return event_id

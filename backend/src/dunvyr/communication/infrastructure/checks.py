"""Stage a public check fact without ending the caller's transaction."""

import json
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from dunvyr.communication.infrastructure.repositories import SqlAlchemyChatEventRepository
from dunvyr.communication.infrastructure.tables import communication_events


class CheckEventStager:
    def __init__(self, session: Session) -> None:
        self.session = session

    def stage(
        self, campaign_id: UUID, result: dict[str, object], now: datetime, facts: tuple[str, ...]
    ) -> UUID:
        event_id = uuid4()
        self.session.execute(
            communication_events.insert().values(
                campaign_id=str(campaign_id),
                event_id=str(event_id),
                kind="check_resolved",
                sequence=SqlAlchemyChatEventRepository(self.session).next_sequence(campaign_id),
                occurred_at=now.isoformat(),
                content=json.dumps(result),
            )
        )
        from dunvyr.communication.infrastructure.narrations import NarrationRepository

        NarrationRepository(self.session).stage(
            campaign_id, event_id, result["success"] is True, facts, now
        )
        return event_id

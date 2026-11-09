"""Gameplay-owned rows; database uniqueness and version CAS, no foreign tables."""

import json
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from dunvyr.gameplay.application.service import QueueCommand, QueueError, project
from dunvyr.gameplay.domain import Queue
from dunvyr.gameplay.public import Participant, QueueSnapshot, QueueState


def decode_state(value: str) -> QueueState:
    data = json.loads(value)
    q = data["queue"]
    return QueueState(
        data["version"],
        None
        if q is None
        else QueueSnapshot(
            q["encounter_id"],
            tuple(Participant(**p) for p in q["participants"]),
            tuple(q["round_order"]),
            q["round_number"],
            q["cursor"],
            tuple(q["skipped"]),
            q["current_guest_id"],
        ),
    )


class SqlQueueUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session

    def campaigns(self) -> tuple[UUID, ...]:
        return tuple(
            UUID(v)
            for v in self.session.execute(text("SELECT campaign_id FROM gameplay_queues")).scalars()
        )

    def load(self, campaign_id: UUID) -> tuple[str, Queue] | None:
        row = self.session.execute(
            text("SELECT encounter_id, content FROM gameplay_queues WHERE campaign_id=:cid"),
            {"cid": str(campaign_id)},
        ).first()
        if row is None:
            return None
        data = json.loads(row.content)
        return row.encounter_id, Queue(
            tuple(tuple(p) for p in data["base_order"]),
            tuple(data["round_order"]),
            data["round_number"],
            data["cursor"],
            tuple(data["skipped"]),
            data["version"],
        )

    def read(self, campaign_id: UUID) -> QueueState:
        value = self.load(campaign_id)
        return QueueState(0, None) if value is None else project(*value)

    def receipt(self, command: QueueCommand) -> tuple[str, QueueState] | None:
        row = self.session.execute(
            text(
                "SELECT payload, response FROM gameplay_receipts "
                "WHERE campaign_id=:cid AND actor_id=:actor AND key=:key"
            ),
            {
                "cid": str(command.campaign_id),
                "actor": str(command.actor_id),
                "key": str(command.key),
            },
        ).first()
        return None if row is None else (row.payload, decode_state(row.response))

    def save(self, campaign_id: UUID, encounter_id: str, queue: Queue, expected: int) -> None:
        params = {
            "cid": str(campaign_id),
            "eid": encounter_id,
            "version": queue.version,
            "content": json.dumps(asdict(queue)),
            "expected": expected,
        }
        if expected == 0:
            result = self.session.execute(
                text(
                    "INSERT INTO gameplay_queues (campaign_id, encounter_id, version, content) "
                    "VALUES (:cid, :eid, :version, :content) ON CONFLICT(campaign_id) DO NOTHING"
                ),
                params,
            )
        else:
            result = self.session.execute(
                text(
                    "UPDATE gameplay_queues SET version=:version, content=:content "
                    "WHERE campaign_id=:cid AND version=:expected"
                ),
                params,
            )
        if getattr(result, "rowcount", 0) != 1:
            raise QueueError(409, "stale_state")

    def record(self, command: QueueCommand, state: QueueState) -> None:
        self.session.execute(
            text(
                "INSERT INTO gameplay_receipts (campaign_id, actor_id, key, payload, response) "
                "VALUES (:cid, :actor, :key, :payload, :response)"
            ),
            {
                "cid": str(command.campaign_id),
                "actor": str(command.actor_id),
                "key": str(command.key),
                "payload": command.payload(),
                "response": json.dumps(asdict(state)),
            },
        )

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()

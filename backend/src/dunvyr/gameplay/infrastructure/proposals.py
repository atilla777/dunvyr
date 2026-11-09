"""Gameplay-owned proposal storage in the calling transaction."""

import json
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from dunvyr.gameplay.application.proposals import (
    ProposalCommand,
    ProposalState,
    ProposalView,
    Selection,
)
from dunvyr.gameplay.application.service import QueueError
from dunvyr.gameplay.domain import ProposalCollection, ProposedAction, Queue
from dunvyr.gameplay.infrastructure.repository import SqlQueueUnitOfWork


class SqlProposalUnitOfWork:
    def __init__(self, session: Session) -> None:
        self.session = session

    def queue(self, campaign_id: UUID) -> Queue | None:
        result = SqlQueueUnitOfWork(self.session).load(campaign_id)
        return result[1] if result else None

    def load(self, campaign_id: UUID, actor_id: UUID) -> ProposalCollection:
        row = self.session.execute(
            text(
                "SELECT version, content FROM gameplay_proposal_collections "
                "WHERE campaign_id=:cid AND actor_id=:actor"
            ),
            {"cid": str(campaign_id), "actor": str(actor_id)},
        ).first()
        if row is None:
            return ProposalCollection(str(actor_id))
        return ProposalCollection(
            str(actor_id), tuple(ProposedAction(**p) for p in json.loads(row.content)), row.version
        )

    def receipt(self, command: ProposalCommand) -> tuple[str, ProposalState] | None:
        row = self.session.execute(
            text(
                "SELECT payload, response FROM gameplay_proposal_receipts "
                "WHERE campaign_id=:cid AND actor_id=:actor AND key=:key"
            ),
            {
                "cid": str(command.campaign_id),
                "actor": str(command.actor_id),
                "key": str(command.key),
            },
        ).first()
        if row is None:
            return None
        data = json.loads(row.response)
        if "result" in data:
            raise QueueError(409, "conflict")
        views = tuple(
            ProposalView(
                p["id"],
                p["character_id"],
                Selection(**p["selection"]) if p["selection"] else None,
                p["availability"],
            )
            for p in data["proposals"]
        )
        return row.payload, ProposalState(data["version"], views)

    def save(self, campaign_id: UUID, collection: ProposalCollection, expected: int) -> None:
        params = {
            "cid": str(campaign_id),
            "actor": collection.owner,
            "version": collection.version,
            "content": json.dumps([asdict(p) for p in collection.proposals]),
            "expected": expected,
        }
        if expected == 0:
            query = (
                "INSERT INTO gameplay_proposal_collections "
                "(campaign_id, actor_id, version, content) "
                "VALUES (:cid, :actor, :version, :content) "
                "ON CONFLICT(campaign_id, actor_id) DO NOTHING"
            )
        else:
            query = (
                "UPDATE gameplay_proposal_collections SET version=:version, content=:content "
                "WHERE campaign_id=:cid AND actor_id=:actor AND version=:expected"
            )
        result = self.session.execute(text(query), params)
        if getattr(result, "rowcount", 0) != 1:
            raise QueueError(409, "stale_state")

    def record(self, command: ProposalCommand, state: ProposalState) -> None:
        self.session.execute(
            text(
                "INSERT INTO gameplay_proposal_receipts "
                "(campaign_id, actor_id, key, payload, response) "
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

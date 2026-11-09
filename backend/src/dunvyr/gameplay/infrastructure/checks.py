"""Gameplay-owned audit and exact confirmation receipts."""

import json
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from dunvyr.gameplay.application.proposals import ProposalCommand


class SqlCheckRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def receipt(self, command: ProposalCommand) -> tuple[str, dict[str, object]] | None:
        row = self.session.execute(
            text(
                "SELECT payload,response FROM gameplay_proposal_receipts "
                "WHERE campaign_id=:cid AND actor_id=:actor AND key=:key"
            ),
            {
                "cid": str(command.campaign_id),
                "actor": str(command.actor_id),
                "key": str(command.key),
            },
        ).first()
        return None if row is None else (row.payload, json.loads(row.response))

    def record(
        self, command: ProposalCommand, audit: dict[str, object], result: dict[str, object]
    ) -> None:
        self.session.execute(
            text("INSERT INTO gameplay_check_audits (campaign_id,content) VALUES (:cid,:content)"),
            {"cid": str(command.campaign_id), "content": json.dumps(audit)},
        )
        self.session.execute(
            text(
                "INSERT INTO gameplay_proposal_receipts "
                "(campaign_id,actor_id,key,payload,response) "
                "VALUES (:cid,:actor,:key,:payload,:response)"
            ),
            {
                "cid": str(command.campaign_id),
                "actor": str(command.actor_id),
                "key": str(command.key),
                "payload": command.payload(),
                "response": json.dumps({"result": result}),
            },
        )

    def latest(self, campaign_id: UUID) -> dict[str, object] | None:
        value = self.session.execute(
            text("SELECT content FROM gameplay_check_audits WHERE campaign_id=:cid"),
            {"cid": str(campaign_id)},
        ).scalar_one_or_none()
        return None if value is None else json.loads(value)["result"]

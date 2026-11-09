"""Communication-owned durable outbox and immutable status events.

All mutation paths acquire SQLite's writer reservation BEFORE reading. No network
operation belongs here, and no foreign context's table is read or written.
"""

from __future__ import annotations

import builtins
import json
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from dunvyr.communication.domain import can_complete_narration, can_retry_narration
from dunvyr.communication.infrastructure.repositories import SqlAlchemyChatEventRepository
from dunvyr.communication.infrastructure.tables import (
    communication_events as events,
)
from dunvyr.communication.infrastructure.tables import (
    communication_narration_retries as retries,
)
from dunvyr.communication.infrastructure.tables import (
    communication_narration_starts as starts,
)
from dunvyr.communication.infrastructure.tables import (
    communication_narrations as requests,
)


class NarrationConflict(ValueError):
    def __init__(self, status: int, detail: str) -> None:
        self.status, self.detail = status, detail


def public_state(row: Any) -> dict[str, Any]:
    return {key: row[key] for key in ("result_event_id", "state", "revision", "text", "error")}


class NarrationRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock(self) -> None:
        # A no-op UPDATE obtains the database writer reservation, including when
        # there are zero requests. The transaction is short and caller-owned.
        self.session.execute(
            update(requests)
            .where(requests.c.result_event_id == "")
            .values(revision=requests.c.revision)
        )

    def get(self, campaign_id: UUID, result_id: UUID) -> Any:
        return (
            self.session.execute(
                select(requests).where(
                    requests.c.campaign_id == str(campaign_id),
                    requests.c.result_event_id == str(result_id),
                )
            )
            .mappings()
            .first()
        )

    def list(self, campaign_id: UUID) -> list[dict[str, Any]]:
        return [
            public_state(row)
            for row in self.session.execute(
                select(requests).where(requests.c.campaign_id == str(campaign_id))
            ).mappings()
        ]

    def current_events(self, campaign_id: UUID) -> builtins.list[dict[str, object]]:
        from dunvyr.communication.application.wire import event_to_wire
        from dunvyr.communication.infrastructure.repositories import _to_event

        rows = self.session.execute(
            select(events)
            .join(
                requests,
                (
                    requests.c.result_event_id
                    == func.json_extract(events.c.content, "$.result_event_id")
                )
                & (requests.c.revision == func.json_extract(events.c.content, "$.revision")),
            )
            .where(events.c.campaign_id == str(campaign_id), events.c.kind == "narration_changed")
            .order_by(events.c.sequence)
        ).mappings()
        return [event_to_wire(_to_event(row)) for row in rows]

    def event(self, row: Any, now: datetime) -> UUID:
        event_id = uuid4()
        self.session.execute(
            events.insert().values(
                campaign_id=row["campaign_id"],
                event_id=str(event_id),
                kind="narration_changed",
                sequence=SqlAlchemyChatEventRepository(self.session).next_sequence(
                    UUID(row["campaign_id"])
                ),
                occurred_at=now.isoformat(),
                content=json.dumps(public_state(row), ensure_ascii=False),
            )
        )
        return event_id

    def stage(
        self,
        campaign_id: UUID,
        result_id: UUID,
        success: bool,
        facts: tuple[str, ...],
        now: datetime,
    ) -> None:
        self.session.execute(
            requests.insert().values(
                campaign_id=str(campaign_id),
                result_event_id=str(result_id),
                context=json.dumps({"success": success, "facts": facts}, ensure_ascii=False),
                state="pending",
                revision=1,
                updated_at=now.timestamp(),
            )
        )
        self.event(self.get(campaign_id, result_id), now)

    def claim(self, now: datetime) -> dict[str, Any] | None:
        self.lock()
        active = list(
            self.session.execute(
                select(requests).where(requests.c.state == "generating")
            ).mappings()
        )
        if len(active) >= 2:
            return None
        busy = {row["campaign_id"] for row in active}
        for row in self.session.execute(
            select(requests)
            .where(requests.c.state == "pending")
            .order_by(requests.c.updated_at, requests.c.result_event_id)
        ).mappings():
            cid = row["campaign_id"]
            count = self.session.execute(
                select(func.count())
                .select_from(starts)
                .where(starts.c.campaign_id == cid, starts.c.started_at > now.timestamp() - 60)
            ).scalar_one()
            if cid in busy or count >= 3:
                continue
            token = str(uuid4())
            changed = self.session.execute(
                update(requests)
                .where(
                    requests.c.result_event_id == row["result_event_id"],
                    requests.c.state == "pending",
                    requests.c.revision == row["revision"],
                )
                .values(
                    state="generating",
                    revision=row["revision"] + 1,
                    attempt_token=token,
                    lease_until=now.timestamp() + 30,
                    updated_at=now.timestamp(),
                    text=None,
                    error=None,
                )
            )
            if getattr(changed, "rowcount", 0) != 1:
                continue
            self.session.execute(
                starts.insert().values(token=token, campaign_id=cid, started_at=now.timestamp())
            )
            self.session.execute(starts.delete().where(starts.c.started_at <= now.timestamp() - 60))
            claim = dict(self.get(UUID(cid), UUID(row["result_event_id"])))
            claim["event_id"] = self.event(claim, now)
            return claim
        return None

    def complete(
        self, claim: dict[str, Any], text: str | None, error: str | None, now: datetime
    ) -> UUID | None:
        self.lock()
        row = self.get(UUID(claim["campaign_id"]), UUID(claim["result_event_id"]))
        if (
            row is None
            or not can_complete_narration(
                row["state"],
                row["revision"],
                row["attempt_token"],
                claim["revision"],
                claim["attempt_token"],
            )
            or row["lease_until"] <= now.timestamp()
        ):
            return None
        self.session.execute(
            update(requests)
            .where(
                requests.c.result_event_id == row["result_event_id"],
                requests.c.revision == claim["revision"],
                requests.c.attempt_token == claim["attempt_token"],
            )
            .values(
                state="failed" if error else "ready",
                revision=row["revision"] + 1,
                text=None if error else text,
                error="retryable_provider_error" if error else None,
                attempt_token=None,
                lease_until=None,
                updated_at=now.timestamp(),
            )
        )
        return self.event(self.get(UUID(row["campaign_id"]), UUID(row["result_event_id"])), now)

    def recover(self, now: datetime) -> builtins.list[tuple[UUID, UUID]]:
        self.lock()
        expired = list(
            self.session.execute(
                select(requests).where(
                    requests.c.state == "generating", requests.c.lease_until <= now.timestamp()
                )
            ).mappings()
        )
        result = []
        for row in expired:
            self.session.execute(
                update(requests)
                .where(
                    requests.c.result_event_id == row["result_event_id"],
                    requests.c.revision == row["revision"],
                )
                .values(
                    state="failed",
                    revision=row["revision"] + 1,
                    attempt_token=None,
                    lease_until=None,
                    text=None,
                    error="retryable_provider_error",
                    updated_at=now.timestamp(),
                )
            )
            cid, rid = UUID(row["campaign_id"]), UUID(row["result_event_id"])
            result.append((cid, self.event(self.get(cid, rid), now)))
        return result

    def retry(
        self,
        campaign_id: UUID,
        actor_id: UUID,
        result_id: UUID,
        key: UUID,
        expected: int,
        now: datetime,
    ) -> tuple[dict[str, Any], UUID | None]:
        self.lock()
        receipt = (
            self.session.execute(
                select(retries).where(
                    retries.c.campaign_id == str(campaign_id),
                    retries.c.actor_id == str(actor_id),
                    retries.c.key == str(key),
                )
            )
            .mappings()
            .first()
        )
        if receipt is not None and (
            receipt["result_event_id"] != str(result_id) or receipt["expected_revision"] != expected
        ):
            raise NarrationConflict(409, "conflict")
        row = self.get(campaign_id, result_id)
        if row is None:
            raise NarrationConflict(404, "not_found")
        if receipt is not None:
            return public_state(row), None
        count = self.session.execute(
            select(func.count())
            .select_from(retries)
            .where(
                retries.c.campaign_id == str(campaign_id),
                retries.c.actor_id == str(actor_id),
                retries.c.created_at > now.timestamp() - 60,
            )
        ).scalar_one()
        if count >= 5:
            raise NarrationConflict(429, "retry_rate_limited")
        event_id = None
        if row["state"] == "failed":
            elapsed = now.timestamp() - row["updated_at"]
            if not can_retry_narration(row["state"], row["revision"], expected, elapsed):
                raise NarrationConflict(
                    409 if row["revision"] != expected else 429,
                    "stale_state" if row["revision"] != expected else "retry_cooldown",
                )
            self.session.execute(
                update(requests)
                .where(
                    requests.c.result_event_id == str(result_id),
                    requests.c.state == "failed",
                    requests.c.revision == expected,
                )
                .values(
                    state="pending",
                    revision=expected + 1,
                    error=None,
                    text=None,
                    updated_at=now.timestamp(),
                )
            )
            row = self.get(campaign_id, result_id)
            event_id = self.event(row, now)
        self.session.execute(
            retries.insert().values(
                campaign_id=str(campaign_id),
                actor_id=str(actor_id),
                key=str(key),
                result_event_id=str(result_id),
                expected_revision=expected,
                created_at=now.timestamp(),
            )
        )
        return public_state(row), event_id

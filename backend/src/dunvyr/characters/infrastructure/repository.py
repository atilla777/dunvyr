"""SQLite-backed character repository."""

import json
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


class CharacterRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, campaign_id: UUID, guest_id: UUID) -> dict[str, object] | None:
        value = self.session.execute(
            text(
                "SELECT content FROM characters_characters "
                "WHERE campaign_id=:campaign AND guest_id=:guest"
            ),
            {"campaign": str(campaign_id), "guest": str(guest_id)},
        ).scalar_one_or_none()
        return cast(dict[str, object], json.loads(value)) if value is not None else None

    def insert(self, campaign_id: UUID, guest_id: UUID, character: dict[str, object]) -> bool:
        try:
            result = self.session.execute(
                text(
                    "INSERT INTO characters_characters (campaign_id, guest_id, content) "
                    "VALUES (:campaign, :guest, :content) ON CONFLICT(campaign_id, guest_id) "
                    "DO NOTHING RETURNING campaign_id"
                ),
                {
                    "campaign": str(campaign_id),
                    "guest": str(guest_id),
                    "content": json.dumps(character, ensure_ascii=False),
                },
            )
            created = result.scalar_one_or_none() is not None
            self.session.commit()
            return created
        except BaseException:
            self.session.rollback()
            raise

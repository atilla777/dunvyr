"""Persistence for adventure-owned snapshots."""

import json
from typing import Literal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session

from dunvyr.adventures.domain.package import (
    project_initial_encounters,
    project_initial_map,
    project_initial_scene,
)
from dunvyr.adventures.infrastructure.package_loader import parse_package
from dunvyr.adventures.public import (
    ArchetypeTemplate,
    AvailableEncounter,
    AvailableEncounterCatalog,
    AvailableSolution,
    Characteristics,
    EncounterCheck,
    PinnedTemplates,
    SkillRating,
    SkillTemplate,
)


class SqlSnapshotReader:
    def __init__(self, session: Session) -> None:
        self._session = session

    def release_read(self) -> None:
        self._session.rollback()

    def available_encounters(self, campaign_id: UUID) -> AvailableEncounterCatalog | None:
        row = self._session.execute(
            text("SELECT content, fingerprint FROM adventures_snapshots WHERE campaign_id = :id"),
            {"id": str(campaign_id)},
        ).one_or_none()
        if row is None:
            return None
        try:
            package = parse_package(json.loads(row.content)).model_dump()
            projection = project_initial_encounters(package, row.fingerprint)
            return AvailableEncounterCatalog(
                fingerprint=projection["fingerprint"],
                current_location_id=projection["current_location_id"],
                encounters=tuple(
                    AvailableEncounter(
                        id=encounter["id"],
                        object_id=encounter["object_id"],
                        name=encounter["name"],
                        description=encounter["description"],
                        solutions=tuple(
                            AvailableSolution(
                                id=solution["id"],
                                name=solution["name"],
                                description=solution["description"],
                                check=EncounterCheck(**solution["check"]),
                            )
                            for solution in encounter["solutions"]
                        ),
                    )
                    for encounter in projection["encounters"]
                ),
            )
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise ValueError("invalid snapshot") from error

    def scene(self, campaign_id: UUID) -> dict[str, object] | None:
        content = self._session.execute(
            text("SELECT content FROM adventures_snapshots WHERE campaign_id = :campaign_id"),
            {"campaign_id": str(campaign_id)},
        ).scalar_one_or_none()
        if content is None:
            return None
        try:
            package = parse_package(json.loads(content)).model_dump()
            return project_initial_scene(package)
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise ValueError("invalid snapshot") from error

    def map(self, campaign_id: UUID) -> dict[str, object] | None:
        row = self._session.execute(
            text(
                "SELECT content, fingerprint FROM adventures_snapshots "
                "WHERE campaign_id = :campaign_id"
            ),
            {"campaign_id": str(campaign_id)},
        ).one_or_none()
        if row is None:
            return None
        try:
            package = parse_package(json.loads(row.content)).model_dump()
            return {"fingerprint": row.fingerprint, **project_initial_map(package)}
        except (ValueError, KeyError, TypeError, RecursionError) as error:
            raise ValueError("invalid snapshot") from error

    def resource(self, campaign_id: UUID, resource_id: str) -> bytes | None:
        result: bytes | None = self._session.execute(
            text(
                "SELECT content FROM adventures_resources "
                "WHERE campaign_id = :campaign_id AND resource_id = :resource_id"
            ),
            {"campaign_id": str(campaign_id), "resource_id": resource_id},
        ).scalar_one_or_none()
        return result

    def public_snapshot(self, campaign_id: UUID) -> dict[str, str] | None:
        row = (
            self._session.execute(
                text(
                    "SELECT adventure_id, fingerprint, title, description "
                    "FROM adventures_snapshots WHERE campaign_id = :campaign_id"
                ),
                {"campaign_id": str(campaign_id)},
            )
            .mappings()
            .one_or_none()
        )
        return dict(row) if row is not None else None

    def templates(self, campaign_id: UUID) -> PinnedTemplates | None:
        content = self._session.execute(
            text("SELECT content FROM adventures_snapshots WHERE campaign_id = :campaign_id"),
            {"campaign_id": str(campaign_id)},
        ).scalar_one_or_none()
        if content is None:
            return None
        data = json.loads(content)
        # This mapping belongs to the stored schema, not the currently installed catalog.
        if (
            not isinstance(data, dict)
            or type(data.get("schema_version")) is not int
            or data["schema_version"] not in (1, 2, 3)
        ):
            raise ValueError("unsupported snapshot schema version")
        if data["schema_version"] in (2, 3):
            try:
                data = parse_package(data).model_dump()
            except ValueError as error:
                raise ValueError(
                    "unsupported snapshot schema version or invalid snapshot"
                ) from error
        return PinnedTemplates(
            skills=tuple(SkillTemplate(**skill) for skill in data["skills"]),
            archetypes=tuple(
                ArchetypeTemplate(
                    id=archetype["id"],
                    name=archetype["name"],
                    characteristics=Characteristics(**archetype["characteristics"]),
                    skills=tuple(
                        SkillRating(skill_id=key, value=value)
                        for key, value in archetype["skills"].items()
                    ),
                )
                for archetype in data["archetypes"]
            ),
        )

    def pin(
        self,
        campaign_id: UUID,
        adventure_id: str,
        fingerprint: str,
        title: str,
        description: str,
        content: str,
        resources: dict[str, bytes],
    ) -> Literal["created", "replay", "conflict"]:
        """Atomically insert a complete snapshot, or compare the existing version."""
        try:
            result = self._session.execute(
                text(
                    "INSERT INTO adventures_snapshots "
                    "(campaign_id, adventure_id, fingerprint, title, description, content) "
                    "VALUES (:campaign_id, :adventure_id, :fingerprint, :title, :description, "
                    ":content) ON CONFLICT(campaign_id) DO NOTHING RETURNING campaign_id"
                ),
                {
                    "campaign_id": str(campaign_id),
                    "adventure_id": adventure_id,
                    "fingerprint": fingerprint,
                    "title": title,
                    "description": description,
                    "content": content,
                },
            )
            if result.scalar_one_or_none() is not None:
                for resource_id, resource in resources.items():
                    self._session.execute(
                        text(
                            "INSERT INTO adventures_resources (campaign_id, resource_id, content) "
                            "VALUES (:campaign_id, :resource_id, :content)"
                        ),
                        {
                            "campaign_id": str(campaign_id),
                            "resource_id": resource_id,
                            "content": resource,
                        },
                    )
                outcome: Literal["created", "replay", "conflict"] = "created"
            else:
                current = self.public_snapshot(campaign_id)
                outcome = (
                    "replay"
                    if current is not None
                    and current["adventure_id"] == adventure_id
                    and current["fingerprint"] == fingerprint
                    else "conflict"
                )
            self._session.commit()
            return outcome
        except BaseException:
            self._session.rollback()
            raise

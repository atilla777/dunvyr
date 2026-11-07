"""Character authorization and creation use cases."""

from dataclasses import asdict
from typing import Protocol
from uuid import UUID, uuid4

from dunvyr.adventures.public import PinnedTemplatesReader
from dunvyr.campaigns.public import CampaignMembershipReader
from dunvyr.characters.domain.character import CharacterInput


class CharacterError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail


class Repository(Protocol):
    def get(self, campaign_id: UUID, guest_id: UUID) -> dict[str, object] | None: ...
    def insert(self, campaign_id: UUID, guest_id: UUID, character: dict[str, object]) -> bool: ...


class CharacterService:
    def __init__(
        self,
        members: CampaignMembershipReader,
        templates: PinnedTemplatesReader,
        repository: Repository,
    ) -> None:
        self.members = members
        self.templates = templates
        self.repository = repository

    def authorize(self, campaign_id: UUID, guest_id: UUID) -> None:
        if self.members.find_member(campaign_id, guest_id) is None:
            raise CharacterError(403, "forbidden")

    def choices(self, campaign_id: UUID, guest_id: UUID) -> dict[str, object]:
        self.authorize(campaign_id, guest_id)
        templates = self.templates.templates(campaign_id)
        if templates is None:
            return {"status": "waiting", "archetypes": []}
        return {
            "status": "ready",
            "archetypes": [asdict(a) for a in templates.archetypes],
            "skills": [asdict(s) for s in templates.skills],
        }

    def get(self, campaign_id: UUID, guest_id: UUID) -> dict[str, object] | None:
        self.authorize(campaign_id, guest_id)
        return self.repository.get(campaign_id, guest_id)

    def create(
        self, campaign_id: UUID, guest_id: UUID, name: str, appearance: str, archetype_id: str
    ) -> tuple[int, dict[str, object]]:
        self.authorize(campaign_id, guest_id)
        templates = self.templates.templates(campaign_id)
        if templates is None:
            raise CharacterError(409, "adventure_required")
        try:
            values = CharacterInput.normalize(name, appearance, archetype_id)
        except ValueError as error:
            raise CharacterError(422, "invalid_character") from error
        archetype = next((a for a in templates.archetypes if a.id == values.archetype_id), None)
        if archetype is None:
            raise CharacterError(422, "invalid_character")
        skills = {s.id: s.name for s in templates.skills}
        result: dict[str, object] = {
            "id": str(uuid4()),
            "campaign_id": str(campaign_id),
            "guest_id": str(guest_id),
            "name": values.name,
            "appearance": values.appearance,
            "archetype_id": archetype.id,
            "archetype_name": archetype.name,
            "characteristics": asdict(archetype.characteristics),
            "skills": [
                {"id": s.skill_id, "name": skills[s.skill_id], "value": s.value}
                for s in archetype.skills
            ],
        }
        created = self.repository.insert(campaign_id, guest_id, result)
        current = self.repository.get(campaign_id, guest_id)
        if current is None:
            raise RuntimeError("character insert lost")
        if any(current[key] != result[key] for key in ("name", "appearance", "archetype_id")):
            raise CharacterError(409, "character_conflict")
        return (201 if created else 200), current

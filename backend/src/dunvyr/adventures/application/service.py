"""Read the public projection of an adventure snapshot."""

import json
from typing import Literal, Protocol
from uuid import UUID

from dunvyr.campaigns.public import CampaignMembershipReader


class SnapshotReader(Protocol):
    def public_snapshot(self, campaign_id: UUID) -> dict[str, str] | None: ...


class AdventureReader:
    def __init__(self, membership: CampaignMembershipReader, snapshots: SnapshotReader) -> None:
        self._membership = membership
        self._snapshots = snapshots

    def read(self, campaign_id: UUID, guest_id: UUID) -> dict[str, object]:
        if self._membership.find_member(campaign_id, guest_id) is None:
            raise PermissionError("forbidden")
        snapshot = self._snapshots.public_snapshot(campaign_id)
        return {"status": "pinned" if snapshot else "waiting", "adventure": snapshot}


class Package(Protocol):
    content: str
    resources: dict[str, bytes]
    fingerprint: str


class Catalog(Protocol):
    def list(self) -> list[dict[str, str]]: ...
    def load(self, adventure_id: str) -> Package | None: ...


class SnapshotWriter(SnapshotReader, Protocol):
    def release_read(self) -> None: ...
    def pin(
        self,
        campaign_id: UUID,
        adventure_id: str,
        fingerprint: str,
        title: str,
        description: str,
        content: str,
        resources: dict[str, bytes],
    ) -> Literal["created", "replay", "conflict"]: ...


class SelectionError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


class AdventureSelector:
    def __init__(
        self, membership: CampaignMembershipReader, snapshots: SnapshotWriter, catalog: Catalog
    ):
        self._membership = membership
        self._snapshots = snapshots
        self._catalog = catalog

    def _organizer(self, campaign_id: UUID, guest_id: UUID) -> None:
        member = self._membership.find_member(campaign_id, guest_id)
        if member is None or member.role != "organizer":
            raise SelectionError(403, "forbidden")

    def catalog(self, campaign_id: UUID, guest_id: UUID) -> list[dict[str, str]]:
        self._organizer(campaign_id, guest_id)
        self._snapshots.release_read()
        return self._catalog.list()

    def select(
        self, campaign_id: UUID, guest_id: UUID, adventure_id: str, fingerprint: str
    ) -> tuple[int, dict[str, object]]:
        self._organizer(campaign_id, guest_id)
        current = self._snapshots.public_snapshot(campaign_id)
        self._snapshots.release_read()
        if current is not None:
            if current["adventure_id"] != adventure_id or current["fingerprint"] != fingerprint:
                raise SelectionError(409, "adventure_conflict")
            return 200, {"status": "pinned", "adventure": current}
        package = self._catalog.load(adventure_id)
        if package is None:
            raise SelectionError(404, "adventure_not_found")
        if package.fingerprint != fingerprint:
            raise SelectionError(409, "stale_fingerprint")
        data = json.loads(package.content)
        outcome = self._snapshots.pin(
            campaign_id,
            adventure_id,
            fingerprint,
            data["title"],
            data["summary"],
            package.content,
            package.resources,
        )
        if outcome == "conflict":
            raise SelectionError(409, "adventure_conflict")
        return (201 if outcome == "created" else 200), {
            "status": "pinned",
            "adventure": self._snapshots.public_snapshot(campaign_id),
        }

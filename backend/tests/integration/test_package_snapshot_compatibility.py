"""The packaged templates match the snapshot's public reader contract."""

import base64
import gzip
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dunvyr.adventures.infrastructure.package_loader import load_package
from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader


@pytest.mark.integration
def test_historical_v2_snapshot_is_canonical_and_preserves_consumers(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "last-shift-v2.json.gz.b64"
    content = gzip.decompress(base64.b64decode(fixture.read_text())).decode("utf-8")
    (tmp_path / "adventure.json").write_text(content)
    image = Path(__file__).resolve().parents[3] / "adventures" / "last-shift" / "airlock.png"
    (tmp_path / "airlock.png").write_bytes(image.read_bytes())
    loaded = load_package(tmp_path)
    assert loaded.content == content
    assert loaded.fingerprint == "48d374545f4b9432549798b21c59c68ef8f48d9ebbd45b454459de1fb8fb4087"
    campaign_id = uuid4()
    with Session(migrated_engine) as session:
        reader = SqlSnapshotReader(session)
        assert (
            reader.pin(campaign_id, "last-shift", loaded.fingerprint, "old", "old", content, {})
            == "created"
        )
        scene = reader.scene(campaign_id)
        map_ = reader.map(campaign_id)
        templates = reader.templates(campaign_id)
        assert scene is not None and scene["name"] == "Приёмный шлюз"
        assert map_ is not None and map_["current_location_id"] == "airlock"
        assert templates is not None and any(skill.id == "repair" for skill in templates.skills)


@pytest.mark.integration
def test_historical_v1_snapshot_scene_is_read_without_catalog(
    migrated_engine: Engine, tmp_path: Path
) -> None:
    # Canonical v1 snapshot from the package at base da8f878b, gzip -n and base64
    # encoded; never generated from the current package or loader at test time.
    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "last-shift-v1.json.gz.b64"
    content = gzip.decompress(base64.b64decode(fixture.read_text())).decode("utf-8")
    (tmp_path / "adventure.json").write_text(content)
    image = Path(__file__).resolve().parents[3] / "adventures" / "last-shift" / "airlock.png"
    (tmp_path / "airlock.png").write_bytes(image.read_bytes())
    loaded = load_package(tmp_path)
    assert loaded.content == content
    assert loaded.fingerprint == "806422761dd5f4eebc2001ffe0f19965368b7513bb4db935b9c834ab5f75d93a"
    campaign_id = uuid4()
    with Session(migrated_engine) as session:
        reader = SqlSnapshotReader(session)
        assert (
            reader.pin(campaign_id, "last-shift", "historical", "old", "old", content, {})
            == "created"
        )
        scene = reader.scene(campaign_id)
        assert scene is not None
        assert scene["name"] == "Приёмный шлюз"
        assert scene["illustration"] == "airlock-image"
        map_ = reader.map(campaign_id)
        assert map_ == {
            "fingerprint": "historical",
            "current_location_id": "airlock",
            "locations": [{"id": "airlock", "name": "Приёмный шлюз", "state": "visited"}],
            "exits": [],
        }
        objects = cast(list[dict[str, Any]], scene["objects"])
        assert [obj["name"] for obj in objects] == ["Терминал", "Шкаф", "Гермодверь"]


@pytest.mark.integration
def test_real_package_snapshot_templates(migrated_engine: Engine) -> None:
    root = Path(__file__).resolve().parents[3] / "adventures" / "last-shift"
    package = load_package(root)
    campaign_id = uuid4()
    with Session(migrated_engine) as session:
        reader = SqlSnapshotReader(session)
        assert (
            reader.pin(
                campaign_id,
                "last-shift",
                package.fingerprint,
                "Последняя смена",
                "",
                package.content,
                package.resources,
            )
            == "created"
        )
        templates = reader.templates(campaign_id)
        assert templates is not None
        assert templates.creation_rules_id == "archetype-budget-v1"
        assert {a.id for a in templates.archetypes} == {"engineer", "scout", "negotiator"}
        assert any(s.id == "repair" and s.characteristic == "intellect" for s in templates.skills)
        assert session.execute(text("SELECT count(*) FROM adventures_resources")).scalar_one() == 1

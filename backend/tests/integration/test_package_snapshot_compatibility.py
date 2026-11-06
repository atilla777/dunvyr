"""The packaged templates match the snapshot's public reader contract."""

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dunvyr.adventures.infrastructure.package_loader import load_package
from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader


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
        assert {a.id for a in templates.archetypes} == {"engineer", "scout", "negotiator"}
        assert any(s.id == "repair" and s.characteristic == "intellect" for s in templates.skills)
        assert session.execute(text("SELECT count(*) FROM adventures_resources")).scalar_one() == 1

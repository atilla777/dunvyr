"""Integration coverage for the adventure selection boundary."""

import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from typing import cast
from uuid import uuid4

import pytest
from alembic import command
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from dunvyr.adventures.infrastructure.catalog import LocalCatalog
from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
from dunvyr.infrastructure.db import create_db_engine
from dunvyr.main import create_app
from tests.integration.support import alembic_config
from tests.integration.test_campaigns import create_campaign, login


@pytest.mark.integration
@pytest.mark.parametrize(
    "bad_json", ['{"number":' + "9" * 5000 + "}", "[" * 2000 + "0" + "]" * 2000]
)
def test_catalog_isolates_decoder_limits(client: TestClient, tmp_path: Path, bad_json: str) -> None:
    source = Path(__file__).resolve().parents[3] / "adventures" / "last-shift"
    root = tmp_path / "packages"
    shutil.copytree(source, root / "last-shift")
    (root / "broken").mkdir()
    (root / "broken" / "adventure.json").write_text(bad_json)
    cast(FastAPI, client.app).state.adventure_catalog = LocalCatalog(root)
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    result = client.get(f"/api/campaigns/{campaign_id}/adventures")
    assert result.status_code == 200
    assert [item["adventure_id"] for item in result.json()["adventures"]] == ["last-shift"]
    result = client.post(
        f"/api/campaigns/{campaign_id}/adventure",
        json={"adventure_id": "broken", "fingerprint": "0" * 64},
        headers={"Origin": "http://localhost:5173"},
    )
    assert result.status_code == 404


@pytest.mark.integration
def test_catalog_and_pin_first_then_replay(client: TestClient) -> None:
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    catalog = client.get(f"/api/campaigns/{campaign_id}/adventures")
    assert catalog.status_code == 200
    item = catalog.json()["adventures"][0]
    assert set(item) == {"adventure_id", "fingerprint", "title", "description", "edition"}
    payload = {key: item[key] for key in ("adventure_id", "fingerprint")}
    url = f"/api/campaigns/{campaign_id}/adventure"
    headers = {"Origin": "http://localhost:5173"}
    first = client.post(url, json=payload, headers=headers)
    assert first.status_code == 201
    assert first.json()["status"] == "pinned"
    assert client.post(url, json=payload, headers=headers).status_code == 200
    conflict = client.post(url, json={**payload, "fingerprint": "0" * 64}, headers=headers)
    assert conflict.status_code == 409
    assert conflict.json() == {"detail": "adventure_conflict"}


@pytest.mark.integration
def test_catalog_fingerprint_detects_changed_source_before_pin(
    client: TestClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    source = Path(__file__).resolve().parents[3] / "adventures" / "last-shift"
    root = tmp_path / "packages"
    shutil.copytree(source, root / "last-shift")
    cast(FastAPI, client.app).state.adventure_catalog = LocalCatalog(root)
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    package = root / "last-shift" / "adventure.json"
    data = json.loads(package.read_text())
    data["title"] = "Changed"
    package.write_text(json.dumps(data))
    response = client.post(
        f"/api/campaigns/{campaign_id}/adventure",
        json={"adventure_id": item["adventure_id"], "fingerprint": item["fingerprint"]},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "stale_fingerprint"}
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM adventures_snapshots")).scalar_one() == 0
        )


@pytest.mark.integration
def test_selection_survives_source_changes_and_restart(
    client: TestClient, migrated_engine: Engine, tmp_path: Path
) -> None:
    source = Path(__file__).resolve().parents[3] / "adventures" / "last-shift"
    root = tmp_path / "packages"
    shutil.copytree(source, root / "last-shift")
    cast(FastAPI, client.app).state.adventure_catalog = LocalCatalog(root)
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    url = f"/api/campaigns/{campaign_id}/adventure"
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    payload = {key: item[key] for key in ("adventure_id", "fingerprint")}
    headers = {"Origin": "http://localhost:5173"}
    assert client.post(url, json=payload, headers=headers).status_code == 201
    with migrated_engine.connect() as connection:
        before = connection.execute(text("SELECT content FROM adventures_snapshots")).scalar_one()
        resources = connection.execute(
            text("SELECT resource_id, content FROM adventures_resources")
        ).all()
    package_path = root / "last-shift" / "adventure.json"
    data = json.loads(package_path.read_text())
    data["title"] = "Changed"
    package_path.write_text(json.dumps(data))
    (root / "last-shift" / data["assets"][0]["path"]).write_bytes(b"broken")
    restarted = create_app(engine=migrated_engine)
    restarted.state.adventure_catalog = LocalCatalog(root)
    with TestClient(restarted) as second:
        second.cookies.update(client.cookies)
        assert second.get(url).json()["adventure"]["title"] == item["title"]
        assert second.post(url, json=payload, headers=headers).status_code == 200
        shutil.rmtree(root)
        assert second.post(url, json=payload, headers=headers).status_code == 200
        assert second.get(url).status_code == 200
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT content FROM adventures_snapshots")).scalar_one()
            == before
        )
        assert (
            connection.execute(text("SELECT resource_id, content FROM adventures_resources")).all()
            == resources
        )


@pytest.mark.integration
def test_selection_acl_validation_origin_and_rate_limit(client: TestClient, tmp_path: Path) -> None:
    login(client)
    created = create_campaign(client).json()
    campaign_id = created["id"]
    url = f"/api/campaigns/{campaign_id}/adventure"
    catalog = f"/api/campaigns/{campaign_id}/adventures"
    headers = {"Origin": "http://localhost:5173"}
    item = client.get(catalog).json()["adventures"][0]
    payload = {key: item[key] for key in ("adventure_id", "fingerprint")}
    assert client.post(url, json=payload).status_code == 403
    assert (
        client.post(url, json=payload, headers={"Origin": "https://evil.test"}).status_code == 403
    )
    assert client.post(url, json={**payload, "extra": 1}, headers=headers).status_code == 422
    invalid = client.post(url, json={**payload, "extra": "SENTINEL_SCRIPT"}, headers=headers)
    assert invalid.status_code == 422
    assert "SENTINEL_SCRIPT" not in invalid.text
    assert (
        client.post(url, json={**payload, "fingerprint": "0" * 64}, headers=headers).status_code
        == 409
    )
    client.cookies.clear()
    assert client.get(catalog).status_code == 403
    assert client.post(url, json=payload, headers=headers).status_code == 403
    login(client, "Боб")
    assert client.get(catalog).status_code == 403
    assert client.post(url, json=payload, headers=headers).status_code == 403
    joined = client.post(
        "/api/campaigns/join", json={"secret": created["invitation"]["secret"]}, headers=headers
    )
    assert joined.status_code == 201
    assert client.get(url).status_code == 200
    assert client.get(catalog).status_code == 403
    assert client.post(url, json=payload, headers=headers).status_code == 403
    responses = [client.post(url, json=payload, headers=headers) for _ in range(12)]
    limited = next(response for response in responses if response.status_code == 429)
    assert int(limited.headers["Retry-After"]) > 0


@pytest.mark.integration
def test_invalid_package_is_controlled_and_never_persisted(
    client: TestClient, migrated_engine: Engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from unittest.mock import Mock

    from dunvyr.adventures.infrastructure import catalog as catalog_module

    warning = Mock()
    monkeypatch.setattr(catalog_module.logger, "warning", warning)
    root = tmp_path / "packages"
    (root / "broken").mkdir(parents=True)
    (root / "broken" / "adventure.json").write_text('{"secret": "SENTINEL"}')
    cast(FastAPI, client.app).state.adventure_catalog = LocalCatalog(root)
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    catalog = client.get(f"/api/campaigns/{campaign_id}/adventures")
    assert catalog.json() == {"adventures": []}
    response = client.post(
        f"/api/campaigns/{campaign_id}/adventure",
        json={"adventure_id": "broken", "fingerprint": "0" * 64},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 404
    assert "SENTINEL" not in response.text and str(tmp_path) not in response.text
    assert warning.called
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM adventures_snapshots")).scalar_one() == 0
        )
        assert (
            connection.execute(text("SELECT count(*) FROM adventures_resources")).scalar_one() == 0
        )


@pytest.mark.integration
def test_member_sees_waiting_before_adventure_is_selected(client: TestClient) -> None:
    login(client)
    campaign_id = create_campaign(client).json()["id"]

    response = client.get(f"/api/campaigns/{campaign_id}/adventure")

    assert response.status_code == 200
    assert response.json() == {"status": "waiting", "adventure": None}


@pytest.mark.integration
def test_waiting_state_requires_membership(client: TestClient) -> None:
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    client.cookies.clear()
    assert client.get(f"/api/campaigns/{campaign_id}/adventure").status_code == 403
    login(client, "Боб")
    assert client.get(f"/api/campaigns/{campaign_id}/adventure").status_code == 403
    assert client.get(f"/api/campaigns/{uuid4()}/adventure").status_code == 403


@pytest.mark.integration
def test_member_receives_only_pinned_public_metadata(
    client: TestClient, migrated_engine: Engine
) -> None:
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO adventures_snapshots "
                "(campaign_id, adventure_id, fingerprint, title, description, content) "
                "VALUES (:campaign, 'shift', 'abc', 'Смена', 'Начало', :content)"
            ),
            {"campaign": campaign_id, "content": '{"secret":"SENTINEL"}'},
        )
    response = client.get(f"/api/campaigns/{campaign_id}/adventure")
    assert response.status_code == 200
    assert response.json() == {
        "status": "pinned",
        "adventure": {
            "adventure_id": "shift",
            "fingerprint": "abc",
            "title": "Смена",
            "description": "Начало",
        },
    }
    assert "SENTINEL" not in response.text


@pytest.mark.integration
def test_upgrade_old_database_preserves_existing_data(tmp_path: Path) -> None:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'old.db'}")
    try:
        config = alembic_config(engine)
        command.upgrade(config, "0005")
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO app_metadata (key, value) VALUES ('old', 'kept')"))
        command.upgrade(config, "head")
        with engine.connect() as connection:
            assert (
                connection.execute(
                    text("SELECT value FROM app_metadata WHERE key='old'")
                ).scalar_one()
                == "kept"
            )
            assert (
                connection.execute(text("SELECT count(*) FROM adventures_snapshots")).scalar_one()
                == 0
            )
    finally:
        engine.dispose()


@pytest.mark.integration
def test_pinned_templates_are_immutable_and_exclude_scenario(migrated_engine: Engine) -> None:
    campaign_id = uuid4()
    content = """{"schema_version":1,
      "skills":[{"id":"repair","name":"Ремонт","characteristic":"intellect"}],
      "archetypes":[{"id":"engineer","name":"Инженер",
      "characteristics":{"strength":1,"agility":2,"intellect":3,"presence":1},
      "skills":{"repair":2}}],"locations":[{"secret":"SENTINEL"}]}"""
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO adventures_snapshots (campaign_id, adventure_id, fingerprint, "
                "title, description, content) VALUES "
                "(:id, 'shift', 'abc', 'title', 'desc', :content)"
            ),
            {"id": str(campaign_id), "content": content},
        )
    with Session(migrated_engine) as session:
        templates = SqlSnapshotReader(session).templates(campaign_id)
    assert templates is not None
    assert templates.creation_rules_id == "archetype-budget-v1"
    assert templates.skills[0].id == "repair"
    assert templates.archetypes[0].characteristics.intellect == 3
    assert "SENTINEL" not in repr(templates)
    with pytest.raises((AttributeError, TypeError)):
        templates.skills[0].id = "changed"  # type: ignore[misc]
    with pytest.raises((AttributeError, TypeError)):
        templates.creation_rules_id = "changed"  # type: ignore[misc]


@pytest.mark.integration
@pytest.mark.parametrize("schema_version", [None, 2, True, "1"])
def test_templates_fail_closed_for_unsupported_snapshot_schema(
    migrated_engine: Engine, schema_version: object
) -> None:
    import json

    campaign_id = uuid4()
    content = json.dumps({"schema_version": schema_version, "skills": [], "archetypes": []})
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO adventures_snapshots (campaign_id, adventure_id, fingerprint, "
                "title, description, content) VALUES "
                "(:id, 'shift', 'abc', 'title', 'desc', :content)"
            ),
            {"id": str(campaign_id), "content": content},
        )
    with (
        Session(migrated_engine) as session,
        pytest.raises(ValueError, match="unsupported snapshot"),
    ):
        SqlSnapshotReader(session).templates(campaign_id)


@pytest.mark.integration
def test_snapshot_write_is_first_wins_and_replay_does_not_replace_resources(
    migrated_engine: Engine,
) -> None:
    campaign_id = uuid4()
    with Session(migrated_engine) as session:
        writer = SqlSnapshotReader(session)
        select = writer.pin
        assert (
            select(campaign_id, "shift", "one", "title", "desc", "{}", {"image": b"one"})
            == "created"
        )
        assert (
            select(campaign_id, "shift", "one", "changed", "changed", "{}", {"image": b"two"})
            == "replay"
        )
        assert (
            select(campaign_id, "shift", "two", "title", "desc", "{}", {"image": b"two"})
            == "conflict"
        )
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT content FROM adventures_resources WHERE campaign_id=:id"),
                {"id": str(campaign_id)},
            ).scalar_one()
            == b"one"
        )


@pytest.mark.integration
def test_resource_insert_failure_rolls_back_snapshot(migrated_engine: Engine) -> None:
    campaign_id = uuid4()
    with Session(migrated_engine) as session, pytest.raises(IntegrityError):
        SqlSnapshotReader(session).pin(
            campaign_id,
            "shift",
            "one",
            "title",
            "desc",
            "{}",
            {"image": None},  # type: ignore[dict-item]
        )
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT count(*) FROM adventures_snapshots WHERE campaign_id=:id"),
                {"id": str(campaign_id)},
            ).scalar_one()
            == 0
        )


@pytest.mark.integration
@pytest.mark.parametrize("fingerprints", [("same", "same"), ("one", "two")])
def test_concurrent_file_sqlite_pins_have_one_winner(
    tmp_path: Path, fingerprints: tuple[str, str]
) -> None:
    engine = create_db_engine(f"sqlite:///{tmp_path / 'concurrent.db'}")
    command.upgrade(alembic_config(engine), "head")
    barrier = Barrier(2)
    campaign_id = uuid4()

    def pin(fingerprint: str) -> str:
        with Session(engine) as session:
            barrier.wait(timeout=10)
            return SqlSnapshotReader(session).pin(
                campaign_id,
                "shift",
                fingerprint,
                "title",
                "desc",
                "{}",
                {"image": fingerprint.encode()},
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(pin, fingerprints))
        assert sorted(results) == sorted(
            ["created", "replay" if fingerprints[0] == fingerprints[1] else "conflict"]
        )
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT s.fingerprint, r.content FROM adventures_snapshots s "
                    "JOIN adventures_resources r ON r.campaign_id=s.campaign_id"
                )
            ).one()
            assert row.content == row.fingerprint.encode()
    finally:
        engine.dispose()

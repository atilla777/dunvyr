"""Pinned catalog ACL, projection and persistence boundary."""

import base64
import copy
import gzip
import json
import shutil
from pathlib import Path
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from dunvyr.adventures.infrastructure.catalog import LocalCatalog
from dunvyr.main import create_app
from tests.integration.test_campaigns import create_campaign, login


@pytest.mark.integration
def test_catalog_acl_safe_projection_corruption_and_no_writes(
    client: TestClient, migrated_engine: Engine
):
    login(client)
    campaign = create_campaign(client).json()
    campaign_id = campaign["id"]
    url = f"/api/campaigns/{campaign_id}/encounters"
    waiting = client.get(url)
    assert waiting.json() == {"status": "waiting", "catalog": None}
    assert waiting.headers["cache-control"] == "private, no-store"
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    assert (
        client.post(
            f"/api/campaigns/{campaign_id}/adventure",
            json={k: item[k] for k in ("adventure_id", "fingerprint")},
            headers={"Origin": "http://localhost:5173"},
        ).status_code
        == 201
    )
    with migrated_engine.begin() as connection:
        data = json.loads(
            connection.execute(text("SELECT content FROM adventures_snapshots")).scalar_one()
        )
        hidden = copy.deepcopy(data["encounters"][0]["solutions"][0])
        hidden.update(id="unavailable-sentinel", name="SECRET_SENTINEL", condition_ids=["not-yet"])
        data["conditions"].append(
            {"id": "not-yet", "fact_id": "terminal-inspected", "expected": True}
        )
        data["encounters"][0]["solutions"].append(hidden)
        content = json.dumps(data)
        connection.execute(
            text("UPDATE adventures_snapshots SET content=:content"), {"content": content}
        )
        before = connection.execute(text("SELECT * FROM adventures_snapshots")).all()
        resources = connection.execute(text("SELECT * FROM adventures_resources")).all()
    response = client.get(url)
    assert response.status_code == 200 and response.headers["cache-control"] == "private, no-store"
    catalog = response.json()["catalog"]
    assert (
        catalog["fingerprint"] == item["fingerprint"]
        and catalog["current_location_id"] == "airlock"
    )
    assert [x["id"] for x in catalog["encounters"][0]["solutions"]] == [
        "repair-terminal",
        "restart-terminal",
    ]
    for secret in (
        "unavailable-sentinel",
        "SECRET_SENTINEL",
        "facts",
        "conditions",
        "outcome",
        "effects",
        "not-yet",
    ):
        assert secret not in response.text
    with migrated_engine.connect() as connection:
        assert connection.execute(text("SELECT * FROM adventures_snapshots")).all() == before
        assert connection.execute(text("SELECT * FROM adventures_resources")).all() == resources
    assert client.get(url + "/unavailable-sentinel").status_code == 404
    assert (
        client.get(f"/api/campaigns/{campaign_id}/scene/resources/secret-image").status_code == 404
    )
    client.cookies.clear()
    for target in (url, f"/api/campaigns/{uuid4()}/encounters"):
        denied = client.get(target)
        assert denied.status_code == 403 and denied.json() == {"detail": "forbidden"}
        assert denied.headers["cache-control"] == "private, no-store"
    login(client, "Другой")
    assert client.get(url).status_code == 403
    assert client.get(f"/api/campaigns/{uuid4()}/encounters").status_code == 403
    assert (
        client.post(
            "/api/campaigns/join",
            json={"secret": campaign["invitation"]["secret"]},
            headers={"Origin": "http://localhost:5173"},
        ).status_code
        == 201
    )
    assert client.get(url).json() == response.json()
    with migrated_engine.begin() as connection:
        connection.execute(
            text("UPDATE adventures_snapshots SET content=:content"),
            {"content": '{"schema_version":999,"secret":"SENTINEL"}'},
        )
    bad = client.get(url)
    assert bad.status_code == 500 and bad.json() == {"detail": "encounters_unavailable"}
    assert bad.headers["cache-control"] == "private, no-store"


@pytest.mark.integration
@pytest.mark.parametrize("version", [1, 2])
def test_legacy_catalog_is_explicitly_empty(
    client: TestClient, migrated_engine: Engine, version: int
):
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    fixture = (
        Path(__file__).resolve().parents[1] / "fixtures" / f"last-shift-v{version}.json.gz.b64"
    )
    content = gzip.decompress(base64.b64decode(fixture.read_text())).decode()
    with migrated_engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO adventures_snapshots "
                "(campaign_id, adventure_id, fingerprint, title, description, content) "
                "VALUES (:id, 'last-shift', 'old', 'old', 'old', :content)"
            ),
            {"id": campaign_id, "content": content},
        )
    assert client.get(f"/api/campaigns/{campaign_id}/encounters").json() == {
        "status": "ready",
        "catalog": {"fingerprint": "old", "current_location_id": "airlock", "encounters": []},
    }


@pytest.mark.integration
def test_encounters_survive_package_edit_deletion_and_restart(
    client: TestClient, migrated_engine: Engine, tmp_path: Path
):
    source = Path(__file__).resolve().parents[3] / "adventures/last-shift"
    root = tmp_path / "packages"
    shutil.copytree(source, root / "last-shift")
    cast(FastAPI, client.app).state.adventure_catalog = LocalCatalog(root)
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    assert (
        client.post(
            f"/api/campaigns/{campaign_id}/adventure",
            json={k: item[k] for k in ("adventure_id", "fingerprint")},
            headers={"Origin": "http://localhost:5173"},
        ).status_code
        == 201
    )
    url = f"/api/campaigns/{campaign_id}/encounters"
    before = client.get(url).json()
    (root / "last-shift/adventure.json").write_text("{}")
    assert client.get(url).json() == before
    shutil.rmtree(root)
    with TestClient(create_app(engine=migrated_engine)) as restarted:
        restarted.cookies.update(client.cookies)
        assert restarted.get(url).json() == before


@pytest.mark.integration
def test_invalid_v3_never_partially_pins(
    client: TestClient, migrated_engine: Engine, tmp_path: Path
):
    source = Path(__file__).resolve().parents[3] / "adventures/last-shift"
    root = tmp_path / "packages"
    shutil.copytree(source, root / "last-shift")
    cast(FastAPI, client.app).state.adventure_catalog = LocalCatalog(root)
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    path = root / "last-shift/adventure.json"
    data = json.loads(path.read_text())
    data["encounters"][0]["solutions"][0]["check"]["skill_id"] = "nonexistent"
    path.write_text(json.dumps(data))
    result = client.post(
        f"/api/campaigns/{campaign_id}/adventure",
        json={k: item[k] for k in ("adventure_id", "fingerprint")},
        headers={"Origin": "http://localhost:5173"},
    )
    assert result.status_code == 404
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM adventures_snapshots")).scalar_one() == 0
        )
        assert (
            connection.execute(text("SELECT count(*) FROM adventures_resources")).scalar_one() == 0
        )

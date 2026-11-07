"""Character creation requires a pinned adventure and campaign membership."""

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from tests.integration.test_campaigns import create_campaign, login


def character_context(client: TestClient) -> tuple[str, dict[str, str], dict[str, object]]:
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    headers = {"Origin": "http://localhost:5173"}
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    assert (
        client.post(
            f"/api/campaigns/{campaign_id}/adventure",
            json={key: item[key] for key in ("adventure_id", "fingerprint")},
            headers=headers,
        ).status_code
        == 201
    )
    body: dict[str, object] = {"name": "Ada", "appearance": "coat", "archetype_id": "engineer"}
    return campaign_id, headers, body


@pytest.mark.integration
def test_custom_allocation_and_canonical_replay(client: TestClient) -> None:
    campaign_id, headers, body = character_context(client)
    url = f"/api/campaigns/{campaign_id}/character"
    choices = client.get(f"/api/campaigns/{campaign_id}/character-templates").json()
    assert choices["creation_rules"] == {
        "id": "archetype-budget-v1",
        "minimum": 0,
        "maximum": 10,
        "relative_limit": 1,
        "characteristic_cost": 2,
        "skill_cost": 1,
    }
    assert next(a for a in choices["archetypes"] if a["id"] == "engineer")["budget"] == 23
    allocation = {
        "characteristics": {"strength": 1, "agility": 3, "intellect": 4, "presence": 1},
        "skills": {"repair": 2, "hacking": 2, "stealth": 1},
    }
    first = client.post(url, json={**body, "allocation": allocation}, headers=headers)
    assert first.status_code == 201
    assert first.json()["characteristics"] == allocation["characteristics"]
    assert {s["id"]: s["value"] for s in first.json()["skills"]} == allocation["skills"]
    equivalent = {**allocation, "skills": {**allocation["skills"], "analysis": 0}}
    replay = client.post(url, json={**body, "allocation": equivalent}, headers=headers)
    assert replay.status_code == 200 and replay.json() == first.json()
    assert client.post(url, json=body, headers=headers).status_code == 409
    invalid = {**allocation, "skills": {**allocation["skills"], "repair": 4}}
    assert client.post(url, json={**body, "allocation": invalid}, headers=headers).json() == {
        "detail": "invalid_character"
    }
    assert client.get(url).json() == first.json()


@pytest.mark.integration
def test_old_request_equals_explicit_default(client: TestClient) -> None:
    campaign_id, headers, body = character_context(client)
    url = f"/api/campaigns/{campaign_id}/character"
    first = client.post(url, json=body, headers=headers)
    allocation = {
        "characteristics": first.json()["characteristics"],
        "skills": {s["id"]: s["value"] for s in first.json()["skills"]},
    }
    replay = client.post(url, json={**body, "allocation": allocation}, headers=headers)
    assert first.status_code == 201
    assert replay.status_code == 200 and replay.json() == first.json()


@pytest.mark.integration
@pytest.mark.parametrize("archetype_id", ["engineer", "scout", "negotiator"])
def test_every_shipped_archetype_remains_a_valid_default(
    client: TestClient, archetype_id: str
) -> None:
    campaign_id, headers, body = character_context(client)
    url = f"/api/campaigns/{campaign_id}/character"
    response = client.post(url, json={**body, "archetype_id": archetype_id}, headers=headers)
    assert response.status_code == 201
    assert response.json()["archetype_id"] == archetype_id


@pytest.mark.integration
def test_legacy_card_is_returned_without_backfill(client: TestClient, migrated_engine) -> None:
    import json

    from sqlalchemy import text

    campaign_id, headers, body = character_context(client)
    url = f"/api/campaigns/{campaign_id}/character"
    card = client.post(url, json=body, headers=headers).json()
    card["skills"].append({"id": "analysis", "name": "Legacy name", "value": 0})
    encoded = json.dumps(card, ensure_ascii=False)
    with migrated_engine.begin() as connection:
        connection.execute(
            text("UPDATE characters_characters SET content=:content WHERE campaign_id=:id"),
            {"content": encoded, "id": campaign_id},
        )
    assert client.get(url).json() == card
    replay = client.post(url, json=body, headers=headers)
    assert replay.status_code == 200 and replay.json() == card
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(
                text("SELECT content FROM characters_characters WHERE campaign_id=:id"),
                {"id": campaign_id},
            ).scalar_one()
            == encoded
        )


@pytest.mark.integration
def test_pinned_creation_survives_catalog_deletion_without_rewriting_snapshot(
    client: TestClient, migrated_engine, tmp_path
) -> None:
    import shutil
    from pathlib import Path
    from typing import cast

    from fastapi import FastAPI
    from sqlalchemy import text

    from dunvyr.adventures.infrastructure.catalog import LocalCatalog

    source = Path(__file__).resolve().parents[3] / "adventures" / "last-shift"
    shutil.copytree(source, tmp_path / "last-shift")
    cast(FastAPI, client.app).state.adventure_catalog = LocalCatalog(tmp_path)
    campaign_id, headers, body = character_context(client)
    with migrated_engine.connect() as connection:
        before = connection.execute(
            text("SELECT content, fingerprint FROM adventures_snapshots WHERE campaign_id=:id"),
            {"id": campaign_id},
        ).one()
    (tmp_path / "last-shift" / "adventure.json").unlink()
    choices = client.get(f"/api/campaigns/{campaign_id}/character-templates")
    assert (
        choices.status_code == 200
        and choices.json()["creation_rules"]["id"] == "archetype-budget-v1"
    )
    result = client.post(f"/api/campaigns/{campaign_id}/character", json=body, headers=headers)
    assert result.status_code == 201
    with migrated_engine.connect() as connection:
        after = connection.execute(
            text("SELECT content, fingerprint FROM adventures_snapshots WHERE campaign_id=:id"),
            {"id": campaign_id},
        ).one()
    assert after == before


@pytest.mark.integration
@pytest.mark.parametrize(
    ("allocation", "detail"),
    [
        (None, "invalid_request"),
        ({"characteristics": {}, "skills": {}}, "invalid_request"),
        (
            {
                "characteristics": {"strength": 2, "agility": 2, "intellect": 4, "presence": 1},
                "skills": {"repair": True},
            },
            "invalid_request",
        ),
        (
            {
                "characteristics": {"strength": 2, "agility": 2, "intellect": 4, "presence": 1},
                "skills": {"repair": {"value": 3, "characteristic": "strength"}},
            },
            "invalid_request",
        ),
        (
            {
                "characteristics": {"strength": 2, "agility": 2, "intellect": 4, "presence": 1},
                "skills": {"repair": 3, "hacking": 2, "unknown": 0},
            },
            "invalid_character",
        ),
        (
            {
                "characteristics": {"strength": 3, "agility": 2, "intellect": 4, "presence": 1},
                "skills": {"repair": 3, "hacking": 2},
            },
            "invalid_character",
        ),
    ],
)
def test_invalid_allocation_has_no_side_effect(
    client: TestClient, allocation: object, detail: str
) -> None:
    campaign_id, headers, body = character_context(client)
    url = f"/api/campaigns/{campaign_id}/character"
    response = client.post(url, json={**body, "allocation": allocation}, headers=headers)
    assert response.status_code == 422 and response.json() == {"detail": detail}
    assert client.get(url).json() is None


@pytest.mark.integration
def test_creation_waits_for_pinned_adventure(client: TestClient) -> None:
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    response = client.post(
        f"/api/campaigns/{campaign_id}/character",
        json={"name": "Ada", "appearance": "Blue coat", "archetype_id": "engineer"},
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "adventure_required"}


@pytest.mark.integration
def test_create_replay_and_conflict(client: TestClient) -> None:
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    headers = {"Origin": "http://localhost:5173"}
    assert (
        client.post(
            f"/api/campaigns/{campaign_id}/adventure",
            json={key: item[key] for key in ("adventure_id", "fingerprint")},
            headers=headers,
        ).status_code
        == 201
    )
    url = f"/api/campaigns/{campaign_id}/character"
    body = {"name": " Ada ", "appearance": " Blue coat ", "archetype_id": "engineer"}
    first = client.post(url, json=body, headers=headers)
    assert first.status_code == 201
    assert first.json()["name"] == "Ada"
    assert first.json()["characteristics"]["intellect"] == 4
    assert client.get(url).json() == first.json()
    replay = client.post(url, json={**body, "name": "Ada"}, headers=headers)
    assert replay.status_code == 200
    assert replay.json() == first.json()
    assert client.post(url, json={**body, "name": "Eve"}, headers=headers).status_code == 409


@pytest.mark.integration
def test_acl_injection_validation_and_templates(client: TestClient, migrated_engine) -> None:
    from sqlalchemy import text

    login(client)
    campaign = create_campaign(client).json()
    campaign_id = campaign["id"]
    headers = {"Origin": "http://localhost:5173"}
    url = f"/api/campaigns/{campaign_id}/character"
    templates_url = f"/api/campaigns/{campaign_id}/character-templates"
    item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
    client.post(
        f"/api/campaigns/{campaign_id}/adventure",
        json={key: item[key] for key in ("adventure_id", "fingerprint")},
        headers=headers,
    )
    choices = client.get(templates_url).json()
    assert choices["status"] == "ready"
    assert "locations" not in str(choices)
    body = {"name": "Ada", "appearance": "Blue coat", "archetype_id": "engineer"}
    assert client.post(url, json=body).status_code == 403
    assert client.post(url, json=body, headers={"Origin": "https://evil.test"}).status_code == 403
    extras: list[dict[str, object]] = [
        {"guest_id": "fake"},
        {"skills": {"repair": 10}},
        {"characteristics": {}},
        {"name": ""},
        {"appearance": " "},
        {"archetype_id": "unknown"},
    ]
    for extra in extras:
        assert client.post(url, json={**body, **extra}, headers=headers).status_code == 422
    with migrated_engine.connect() as connection:
        assert (
            connection.execute(text("SELECT count(*) FROM characters_characters")).scalar_one() == 0
        )
    assert client.post(url, json=body, headers=headers).status_code == 201
    client.cookies.clear()
    assert client.get(url).status_code == 403
    assert client.get(templates_url).status_code == 403
    assert client.post(url, json=body, headers=headers).status_code == 403
    login(client, "Bob")
    assert client.get(url).status_code == 403
    assert client.post(url, json=body, headers=headers).status_code == 403
    assert (
        client.post(
            "/api/campaigns/join",
            json={"secret": campaign["invitation"]["secret"]},
            headers=headers,
        ).status_code
        == 201
    )
    assert client.get(url).json() is None
    second = client.post(url, json={**body, "name": "Bob"}, headers=headers)
    assert second.status_code == 201
    assert second.json()["name"] == "Bob"
    assert client.get(url).json() == second.json()


@pytest.mark.integration
@pytest.mark.parametrize("different", [False, True])
def test_concurrent_replay_and_restart(tmp_path, different: bool) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from typing import cast

    from dunvyr.infrastructure.db import create_db_engine
    from dunvyr.main import create_app
    from tests.integration.support import apply_migrations

    engine = create_db_engine(f"sqlite:///{tmp_path / 'characters.db'}")
    apply_migrations(engine)
    app = create_app(engine=engine)
    headers = {"Origin": "http://localhost:5173"}
    with TestClient(app) as client:
        login(client)
        campaign_id = create_campaign(client).json()["id"]
        item = client.get(f"/api/campaigns/{campaign_id}/adventures").json()["adventures"][0]
        assert (
            client.post(
                f"/api/campaigns/{campaign_id}/adventure",
                json={key: item[key] for key in ("adventure_id", "fingerprint")},
                headers=headers,
            ).status_code
            == 201
        )
        cookies = dict(client.cookies)
    url = f"/api/campaigns/{campaign_id}/character"
    allocation = {
        "characteristics": {"strength": 1, "agility": 3, "intellect": 4, "presence": 1},
        "skills": {"repair": 2, "hacking": 2, "stealth": 1},
    }
    body = {
        "name": "Ada",
        "appearance": "Blue coat",
        "archetype_id": "engineer",
        "allocation": allocation,
    }
    barrier = Barrier(2)

    def create(index: int) -> Response:
        with TestClient(app) as guest:
            guest.cookies.update(cookies)
            barrier.wait()
            request = (
                {
                    **body,
                    "allocation": {**allocation, "skills": {"repair": 3, "hacking": 2}},
                }
                if different and index
                else body
            )
            return cast(Response, guest.post(url, json=request, headers=headers))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(create, range(2)))
    assert sorted(result.status_code for result in results) == (
        [201, 409] if different else [200, 201]
    )
    winner = next(result.json() for result in results if result.status_code == 201)
    if not different:
        assert results[0].json() == results[1].json()
    engine.dispose()
    restarted_engine = create_db_engine(f"sqlite:///{tmp_path / 'characters.db'}")
    with TestClient(create_app(engine=restarted_engine)) as guest:
        guest.cookies.update(cookies)
        assert guest.get(url).json() == winner
    restarted_engine.dispose()


@pytest.mark.integration
def test_character_rate_limit(client: TestClient) -> None:
    login(client)
    campaign_id = create_campaign(client).json()["id"]
    url = f"/api/campaigns/{campaign_id}/character"
    body = {"name": "Ada", "appearance": "coat", "archetype_id": "engineer"}
    headers = {"Origin": "http://localhost:5173"}
    responses = [client.post(url, json=body, headers=headers) for _ in range(11)]
    assert responses[-1].status_code == 429
    assert int(responses[-1].headers["Retry-After"]) > 0

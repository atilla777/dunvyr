"""Character creation requires a pinned adventure and campaign membership."""

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from tests.integration.test_campaigns import create_campaign, login


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
def test_concurrent_replay_and_restart(tmp_path) -> None:
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
    body = {"name": "Ada", "appearance": "Blue coat", "archetype_id": "engineer"}
    barrier = Barrier(2)

    def create() -> Response:
        with TestClient(app) as guest:
            guest.cookies.update(cookies)
            barrier.wait()
            return cast(Response, guest.post(url, json=body, headers=headers))

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: create(), range(2)))
    assert sorted(result.status_code for result in results) == [200, 201]
    assert results[0].json() == results[1].json()
    engine.dispose()
    restarted_engine = create_db_engine(f"sqlite:///{tmp_path / 'characters.db'}")
    with TestClient(create_app(engine=restarted_engine)) as guest:
        guest.cookies.update(cookies)
        assert guest.get(url).json() == results[0].json()
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

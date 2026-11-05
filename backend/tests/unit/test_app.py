"""Unit tests for the FastAPI application factory."""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from dunvyr.main import create_app


@pytest.mark.unit
def test_create_app_returns_fastapi_with_project_metadata() -> None:
    app = create_app(database_url="sqlite+pysqlite:///:memory:")

    assert isinstance(app, FastAPI)
    assert app.title == "Dunvyr"


@pytest.mark.unit
def test_create_app_registers_health_route() -> None:
    app = create_app(database_url="sqlite+pysqlite:///:memory:")

    paths = app.openapi()["paths"]
    assert "/health" in paths
    assert "get" in paths["/health"]


@pytest.mark.unit
def test_create_app_registers_identity_routes() -> None:
    app = create_app(database_url="sqlite+pysqlite:///:memory:")

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/identity/sessions"]
    assert "get" in paths["/api/identity/me"]


@pytest.mark.unit
def test_create_app_registers_campaign_routes() -> None:
    app = create_app(database_url="sqlite+pysqlite:///:memory:")

    paths = app.openapi()["paths"]
    assert "post" in paths["/api/campaigns"]
    assert "get" in paths["/api/campaigns/{campaign_id}"]


@pytest.mark.unit
def test_create_app_rejects_engine_and_url_together() -> None:
    from dunvyr.infrastructure.db import create_db_engine

    engine = create_db_engine("sqlite+pysqlite:///:memory:")
    try:
        with pytest.raises(ValueError, match="either an engine or a database URL"):
            create_app(engine=engine, database_url="sqlite+pysqlite:///:memory:")
    finally:
        engine.dispose()

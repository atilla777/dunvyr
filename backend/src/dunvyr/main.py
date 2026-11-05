"""Application composition root: builds the FastAPI app from configuration."""

from __future__ import annotations

import os

from fastapi import FastAPI
from sqlalchemy.engine import Engine

from dunvyr import __version__
from dunvyr.infrastructure.db import (
    DEFAULT_DATABASE_URL,
    create_db_engine,
    create_session_factory,
)
from dunvyr.presentation.health import router as health_router


def create_app(
    *,
    engine: Engine | None = None,
    database_url: str | None = None,
) -> FastAPI:
    """Build the application.

    The engine may be injected (tests use a migrated in-memory SQLite engine);
    otherwise the database URL comes from the argument, then from
    ``DUNVYR_DATABASE_URL``, then from the local default.
    """
    if engine is not None and database_url is not None:
        raise ValueError("Pass either an engine or a database URL, not both")

    resolved_url = database_url or os.environ.get("DUNVYR_DATABASE_URL", DEFAULT_DATABASE_URL)
    resolved_engine = engine if engine is not None else create_db_engine(resolved_url)

    app = FastAPI(title="Dunvyr", version=__version__)
    app.state.engine = resolved_engine
    app.state.session_factory = create_session_factory(resolved_engine)
    app.state.database_url = resolved_url
    app.include_router(health_router)
    return app

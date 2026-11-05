"""Application composition root: builds the FastAPI app from configuration."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine

from dunvyr import __version__
from dunvyr.identity.application.rate_limit import RateLimitPolicy, SlidingWindowRateLimiter
from dunvyr.identity.infrastructure.clock import utc_now
from dunvyr.identity.infrastructure.factory import build_identity_service
from dunvyr.identity.presentation.config import AllowedOrigins, env_flag
from dunvyr.identity.presentation.router import router as identity_router
from dunvyr.infrastructure.db import (
    DEFAULT_DATABASE_URL,
    create_db_engine,
    create_session_factory,
)
from dunvyr.infrastructure.migrations import run_migrations
from dunvyr.presentation.health import router as health_router


def create_app(
    *,
    engine: Engine | None = None,
    database_url: str | None = None,
) -> FastAPI:
    """Build the application.

    The engine may be injected (tests use a migrated in-memory SQLite engine);
    otherwise the database URL comes from the argument, then from
    ``DUNVYR_DATABASE_URL``, then from the local default. With
    ``DUNVYR_AUTO_MIGRATE=1`` the real Alembic pipeline upgrades that engine to
    head before the app starts serving.
    """
    if engine is not None and database_url is not None:
        raise ValueError("Pass either an engine or a database URL, not both")

    resolved_url = database_url or os.environ.get("DUNVYR_DATABASE_URL", DEFAULT_DATABASE_URL)
    resolved_engine = engine if engine is not None else create_db_engine(resolved_url)

    if env_flag(os.environ.get("DUNVYR_AUTO_MIGRATE")):
        run_migrations(resolved_engine, os.environ.get("DUNVYR_MIGRATIONS_DIR"))

    allowed_origins = AllowedOrigins.parse(os.environ.get("DUNVYR_ALLOWED_ORIGINS"))

    app = FastAPI(title="Dunvyr", version=__version__)
    app.state.engine = resolved_engine
    app.state.session_factory = create_session_factory(resolved_engine)
    app.state.database_url = resolved_url
    app.state.allowed_origins = allowed_origins
    app.state.cookie_secure = env_flag(os.environ.get("DUNVYR_COOKIE_SECURE"))
    app.state.rate_limiter = SlidingWindowRateLimiter(policy=RateLimitPolicy(), clock=utc_now)
    app.state.identity_service_factory = build_identity_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins.origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type"],
    )

    app.include_router(health_router)
    app.include_router(identity_router)
    return app

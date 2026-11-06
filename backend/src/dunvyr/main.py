"""Application composition root: builds the FastAPI app from configuration."""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from dunvyr import __version__
from dunvyr.adventures.application.service import AdventureReader, AdventureSelector
from dunvyr.adventures.infrastructure.catalog import LocalCatalog
from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
from dunvyr.adventures.presentation.router import router as adventures_router
from dunvyr.campaigns.application.rate_limit import (
    CampaignRateLimitPolicy,
    CampaignSlidingWindowRateLimiter,
)
from dunvyr.campaigns.infrastructure.factory import build_campaign_service
from dunvyr.campaigns.infrastructure.membership import build_campaign_membership_reader
from dunvyr.campaigns.presentation.router import router as campaigns_router
from dunvyr.communication.application.service import ChatService
from dunvyr.communication.infrastructure.campaign_events import (
    build_campaign_member_joined_publisher,
)
from dunvyr.communication.infrastructure.factory import build_chat_service
from dunvyr.communication.infrastructure.realtime import RealtimeHub
from dunvyr.communication.presentation.router import router as communication_router
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
    app.state.campaign_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(),
        clock=utc_now,
    )
    app.state.adventure_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(), clock=utc_now
    )
    app.state.adventure_catalog = LocalCatalog(
        Path(
            os.environ.get(
                "DUNVYR_ADVENTURES_ROOT", Path(__file__).resolve().parents[3] / "adventures"
            )
        )
    )
    app.state.pinned_templates_reader_factory = SqlSnapshotReader
    app.state.identity_service_factory = build_identity_service
    app.state.guest_resolver_factory = build_identity_service
    app.state.campaign_membership_reader_factory = build_campaign_membership_reader
    app.state.adventure_reader_factory = lambda session: AdventureReader(
        build_campaign_membership_reader(session), SqlSnapshotReader(session)
    )
    app.state.adventure_selector_factory = lambda session: AdventureSelector(
        build_campaign_membership_reader(session),
        SqlSnapshotReader(session),
        app.state.adventure_catalog,
    )

    realtime_hub = RealtimeHub()
    app.state.realtime_hub = realtime_hub

    def chat_service_factory(session: Session) -> ChatService:
        return build_chat_service(
            session,
            membership_reader=build_campaign_membership_reader(session),
        )

    app.state.chat_service_factory = chat_service_factory
    app.state.campaign_service_factory = build_campaign_service
    app.state.campaign_event_publisher = build_campaign_member_joined_publisher(
        app.state.session_factory,
        realtime_hub,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins.origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Idempotency-Key"],
    )

    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(campaigns_router)
    app.include_router(adventures_router)
    app.include_router(communication_router)
    return app

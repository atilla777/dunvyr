"""Application composition root: builds the FastAPI app from configuration."""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from threading import Lock
from uuid import uuid4
from weakref import WeakKeyDictionary

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker
from sqlalchemy.pool import StaticPool

from dunvyr import __version__
from dunvyr.adventures.application.service import AdventureReader, AdventureSelector
from dunvyr.adventures.infrastructure.catalog import LocalCatalog
from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader
from dunvyr.adventures.presentation.router import router as adventures_router
from dunvyr.campaigns.application.game_sessions import GameSessionService
from dunvyr.campaigns.application.presence import PresenceRuntime
from dunvyr.campaigns.application.rate_limit import (
    CampaignRateLimitPolicy,
    CampaignSlidingWindowRateLimiter,
)
from dunvyr.campaigns.infrastructure.factory import build_campaign_service
from dunvyr.campaigns.infrastructure.game_sessions import SqlGameSessionUnitOfWork
from dunvyr.campaigns.infrastructure.membership import build_campaign_membership_reader
from dunvyr.campaigns.presentation.game_sessions import router as game_sessions_router
from dunvyr.campaigns.presentation.router import router as campaigns_router
from dunvyr.characters.application.service import CharacterService
from dunvyr.characters.infrastructure.eligibility import SqlCharacterEligibilityReader
from dunvyr.characters.infrastructure.repository import CharacterRepository
from dunvyr.characters.presentation.router import router as characters_router
from dunvyr.communication.application.service import ChatService
from dunvyr.communication.infrastructure.campaign_events import (
    build_campaign_member_joined_publisher,
)
from dunvyr.communication.infrastructure.checks import CheckEventStager
from dunvyr.communication.infrastructure.factory import build_chat_service
from dunvyr.communication.infrastructure.game_sessions import (
    GameSessionEventStager,
    GameSessionNotifier,
)
from dunvyr.communication.infrastructure.proposals import ProposalNotifier
from dunvyr.communication.infrastructure.queues import QueueEventStager
from dunvyr.communication.infrastructure.realtime import RealtimeHub
from dunvyr.communication.presentation.router import router as communication_router
from dunvyr.gameplay.application.confirmation import ConfirmationService
from dunvyr.gameplay.application.proposals import ProposalService
from dunvyr.gameplay.application.service import QueueService
from dunvyr.gameplay.infrastructure.checks import SqlCheckRepository
from dunvyr.gameplay.infrastructure.proposals import SqlProposalUnitOfWork
from dunvyr.gameplay.infrastructure.repository import SqlQueueUnitOfWork
from dunvyr.gameplay.presentation.proposals import router as proposals_router
from dunvyr.gameplay.presentation.router import router as queue_router
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

_memory_locks: WeakKeyDictionary[Engine, Lock] = WeakKeyDictionary()
_memory_registry_lock = Lock()


def _app_sessions(engine: Engine) -> sessionmaker[Session]:
    sessions = create_session_factory(engine)
    if not isinstance(engine.pool, StaticPool):
        return sessions
    # The in-memory engine has ONE DBAPI connection. Concurrent Sessions cannot
    # own independent transactions on it: even closing a reader rolls back a
    # writer. Serialize application transactions only for this transient mode.
    # File SQLite still uses independent connections, owner locks and SQL CAS.
    with _memory_registry_lock:
        lock = _memory_locks.setdefault(engine, Lock())

    def begin(session: Session, transaction: SessionTransaction) -> None:
        if transaction.parent is None:
            lock.acquire()

    def end(session: Session, transaction: SessionTransaction) -> None:
        if transaction.parent is None:
            lock.release()

    event.listen(sessions, "after_transaction_create", begin)
    event.listen(sessions, "after_transaction_end", end)
    return sessions


def create_app(
    *,
    engine: Engine | None = None,
    database_url: str | None = None,
    presence_ping_interval: float = 10.0,
    presence_pong_timeout: float = 20.0,
    presence_lease: float = 30.0,
    presence_grace: float = 5.0,
    presence_sweep_interval: float = 1.0,
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

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()

        def reconcile_queues() -> None:
            try:
                with app.state.session_factory() as session:
                    campaign_ids = SqlQueueUnitOfWork(session).campaigns()
            except Exception:
                logging.getLogger(__name__).exception("Could not enumerate durable queues")
                return
            for campaign_id in campaign_ids:
                try:
                    with app.state.session_factory() as session:
                        app.state.queue_service_factory(session).reconcile(campaign_id)
                except Exception:
                    logging.getLogger(__name__).exception(
                        "Queue reconciliation failed; retrying next sweep"
                    )

        async def sweep() -> None:
            while not stop.is_set():
                with suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=presence_sweep_interval)
                if stop.is_set():
                    break
                app.state.presence.sweep()
                await asyncio.to_thread(reconcile_queues)

        task = asyncio.create_task(sweep())
        try:
            yield
        finally:
            stop.set()
            await task

    app = FastAPI(title="Dunvyr", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def private_proposals(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        parts = request.url.path.split("/")
        if (
            len(parts) >= 5
            and parts[1:3] == ["api", "campaigns"]
            and parts[4] in {"proposals", "check-result"}
        ):
            response.headers["Cache-Control"] = "private, no-store"
        return response

    app.state.engine = resolved_engine
    app.state.session_factory = _app_sessions(resolved_engine)
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
    app.state.character_rate_limiter = CampaignSlidingWindowRateLimiter(
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
    app.state.character_service_factory = lambda session: CharacterService(
        build_campaign_membership_reader(session),
        SqlSnapshotReader(session),
        CharacterRepository(session),
    )
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
    app.state.presence = PresenceRuntime(realtime_hub, lease=presence_lease, grace=presence_grace)
    app.state.presence_ping_interval = presence_ping_interval
    app.state.presence_pong_timeout = presence_pong_timeout
    app.state.game_session_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(),
        clock=utc_now,
    )
    app.state.game_session_reader_factory = SqlGameSessionUnitOfWork
    app.state.queue_reader_factory = SqlQueueUnitOfWork
    app.state.queue_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(),
        clock=utc_now,
    )
    app.state.proposal_rate_limiter = CampaignSlidingWindowRateLimiter(
        policy=CampaignRateLimitPolicy(), clock=utc_now
    )
    app.state.proposal_service_factory = lambda session: ProposalService(
        SqlProposalUnitOfWork(session),
        SqlGameSessionUnitOfWork(session),
        SqlCharacterEligibilityReader(CharacterRepository(session), SqlSnapshotReader(session)),
        SqlSnapshotReader(session),
        app.state.presence,
        ProposalNotifier(realtime_hub),
    )
    app.state.confirmation_service_factory = lambda session: ConfirmationService(
        SqlProposalUnitOfWork(session),
        SqlQueueUnitOfWork(session),
        SqlCheckRepository(session),
        SqlGameSessionUnitOfWork(session),
        SqlCharacterEligibilityReader(CharacterRepository(session), SqlSnapshotReader(session)),
        SqlSnapshotReader(session),
        SqlSnapshotReader(session),
        app.state.presence,
        CheckEventStager(session),
        GameSessionNotifier(app.state.session_factory, realtime_hub),
        utc_now,
        lambda: tuple(secrets.randbelow(3) - 1 for _ in range(4)),
    )
    app.state.queue_service_factory = lambda session: QueueService(
        SqlQueueUnitOfWork(session),
        SqlGameSessionUnitOfWork(session),
        SqlCharacterEligibilityReader(CharacterRepository(session), SqlSnapshotReader(session)),
        SqlSnapshotReader(session),
        QueueEventStager(session),
        GameSessionNotifier(app.state.session_factory, realtime_hub),
        utc_now,
        app.state.presence,
    )
    app.state.game_session_service_factory = lambda session: GameSessionService(
        SqlGameSessionUnitOfWork(session),
        GameSessionEventStager(session),
        GameSessionNotifier(app.state.session_factory, realtime_hub),
        utc_now,
        uuid4,
    )

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
    app.include_router(game_sessions_router)
    app.include_router(queue_router)
    app.include_router(proposals_router)
    app.include_router(adventures_router)
    app.include_router(characters_router)
    app.include_router(communication_router)
    return app

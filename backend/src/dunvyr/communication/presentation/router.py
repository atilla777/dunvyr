"""Campaign chat WebSocket stream plus member-only REST history snapshot."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from dataclasses import asdict, dataclass, field
from typing import Annotated, Any, cast
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Query, Request, WebSocket, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from dunvyr.campaigns.public import (
    CampaignMemberSnapshot,
    GameSessionReader,
    PresenceObserver,
    PresenceReader,
)
from dunvyr.communication.application.errors import (
    ClientMessageConflict,
    EventAppendConflict,
    NotAMember,
)
from dunvyr.communication.application.service import ChatService, SendMessage, SendMessageResult
from dunvyr.communication.application.wire import event_to_wire
from dunvyr.communication.domain.message import InvalidMessage
from dunvyr.communication.infrastructure.realtime import RealtimeHub
from dunvyr.communication.presentation.config import OriginAllowList
from dunvyr.communication.presentation.dependencies import get_chat_service, get_current_guest
from dunvyr.communication.presentation.schemas import ChatHistoryResponse
from dunvyr.gameplay.public import QueueReader
from dunvyr.identity.public import SESSION_COOKIE_NAME, GuestResolver, GuestSnapshot
from dunvyr.infrastructure.db import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/campaigns", tags=["communication"])

WS_POLICY_VIOLATION = 4403

Service = Annotated[ChatService, Depends(get_chat_service)]
Guest = Annotated[GuestSnapshot, Depends(get_current_guest)]
AfterSequence = Annotated[int | None, Query(ge=0)]


def _resolve_guest(app: FastAPI, session_token: str | None) -> GuestSnapshot | None:
    factory: Callable[[Session], GuestResolver] = app.state.guest_resolver_factory
    with app.state.session_factory() as session:
        return factory(session).resolve_guest(session_token)


def _find_member(
    app: FastAPI,
    campaign_id: UUID,
    guest_id: UUID,
) -> CampaignMemberSnapshot | None:
    factory: Callable[[Session], Any] = app.state.campaign_membership_reader_factory
    with app.state.session_factory() as session:
        reader = factory(session)
        return cast(CampaignMemberSnapshot | None, reader.find_member(campaign_id, guest_id))


def _send_message_sync(app: FastAPI, command: SendMessage) -> SendMessageResult:
    factory: Callable[[Session], ChatService] = app.state.chat_service_factory
    with app.state.session_factory() as session:
        return factory(session).send_message(command)


async def _send_error(websocket: WebSocket, code: str, detail: str) -> None:
    await websocket.send_json({"type": "error", "code": code, "detail": detail})


async def _pump(
    websocket: WebSocket,
    queue: asyncio.Queue[dict[str, object]],
    app: FastAPI,
    campaign_id: UUID,
    guest_id: UUID,
    session_token: str | None,
) -> None:
    while True:
        payload = await queue.get()
        if payload.get("type") == "proposals_changed":
            guest = await run_in_threadpool(_resolve_guest, app, session_token)
            member = await run_in_threadpool(_find_member, app, campaign_id, guest_id)
            if guest is None or guest.id != guest_id or member is None:
                await websocket.close(code=WS_POLICY_VIOLATION)
                return
        await websocket.send_json(payload)


def _consume_task(task: asyncio.Task[None]) -> None:
    """Retrieve a finished task outcome without raising during connection close."""
    if task.cancelled():
        return
    with suppress(Exception):
        task.exception()


async def _handle_text(
    websocket: WebSocket,
    app: FastAPI,
    campaign_id: UUID,
    guest_id: UUID,
    raw: str,
) -> bool:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError, TypeError:
        await _send_error(websocket, "invalid_message", "Message frame must be valid JSON")
        return True

    if not isinstance(payload, dict) or payload.get("type") != "message":
        await _send_error(websocket, "invalid_message", "Only message frames are accepted")
        return True

    try:
        client_message_id = UUID(str(payload["client_message_id"]))
    except KeyError, ValueError, TypeError:
        await _send_error(websocket, "invalid_message", "client_message_id must be a UUID")
        return True

    content = payload.get("content")
    if not isinstance(content, str):
        await _send_error(websocket, "invalid_message", "content must be a string")
        return True

    try:
        result = await run_in_threadpool(
            _send_message_sync,
            app,
            SendMessage(
                campaign_id=campaign_id,
                author_id=guest_id,
                client_message_id=client_message_id,
                content=content,
            ),
        )
    except NotAMember:
        await _send_error(websocket, "forbidden", "Not a campaign member")
        await websocket.close(code=WS_POLICY_VIOLATION)
        return False
    except ClientMessageConflict:
        await _send_error(websocket, "conflict", "client_message_id already used by another author")
        return True
    except InvalidMessage as error:
        await _send_error(websocket, "invalid_message", str(error))
        return True
    except EventAppendConflict:
        await _send_error(websocket, "retryable", "Message could not be appended; retry")
        return True
    except Exception:
        logger.exception("Failed to persist a chat message")
        await _send_error(websocket, "internal", "Message could not be saved")
        return True

    hub: RealtimeHub = app.state.realtime_hub
    if result.created:
        try:
            hub.broadcast(campaign_id, event_to_wire(result.event))
        except Exception:
            # The message is already committed: never roll it back for delivery.
            logger.warning("Failed to broadcast a committed chat message", exc_info=True)
            await _send_error(websocket, "delivery_failed", "Message saved but not delivered")
            return True
    else:
        # A replay must not duplicate the event for already connected clients.
        await websocket.send_json(
            {"type": "ack", "event_id": str(result.event.event_id)},
        )
    return True


@dataclass
class Heartbeat:
    nonce: str | None = None
    received: asyncio.Event = field(default_factory=asyncio.Event)


async def _heartbeat(
    app: FastAPI, queue: asyncio.Queue[dict[str, object]], heartbeat: Heartbeat
) -> None:
    while True:
        await asyncio.sleep(app.state.presence_ping_interval)
        heartbeat.nonce = str(uuid4())
        heartbeat.received.clear()
        await queue.put({"type": "ping", "nonce": heartbeat.nonce})
        await asyncio.wait_for(heartbeat.received.wait(), timeout=app.state.presence_pong_timeout)
        heartbeat.nonce = None


async def _receive_loop(
    websocket: WebSocket,
    app: FastAPI,
    campaign_id: UUID,
    guest_id: UUID,
    connection_id: UUID,
    session_token: str | None,
    heartbeat: Heartbeat,
) -> None:
    while True:
        raw = await websocket.receive_text()
        try:
            payload = json.loads(raw)
        except ValueError, TypeError:
            payload = None
        if isinstance(payload, dict) and payload.get("type") == "pong":
            if heartbeat.nonce is not None and payload.get("nonce") == heartbeat.nonce:
                guest = await run_in_threadpool(_resolve_guest, app, session_token)
                member = await run_in_threadpool(_find_member, app, campaign_id, guest_id)
                presence: PresenceObserver = app.state.presence
                if guest is None or guest.id != guest_id or member is None:
                    await websocket.close(code=WS_POLICY_VIOLATION)
                    return
                if not presence.renew(connection_id):
                    return
                heartbeat.nonce = None
                heartbeat.received.set()
            continue
        if not await _handle_text(websocket, app, campaign_id, guest_id, raw):
            return


@router.websocket("/{campaign_id}/chat")
async def campaign_chat(websocket: WebSocket, campaign_id: UUID) -> None:
    """Authorize the handshake, then stream and accept campaign chat messages."""
    app = cast(FastAPI, websocket.app)
    allowed: OriginAllowList = app.state.allowed_origins
    origin = websocket.headers.get("origin")
    if origin is None or not allowed.contains(origin):
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    guest = await run_in_threadpool(
        _resolve_guest,
        app,
        websocket.cookies.get(SESSION_COOKIE_NAME),
    )
    if guest is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    membership = await run_in_threadpool(_find_member, app, campaign_id, guest.id)
    if membership is None:
        await websocket.close(code=WS_POLICY_VIOLATION)
        return

    hub: RealtimeHub = app.state.realtime_hub
    token, queue = hub.subscribe(campaign_id, guest.id)
    tasks: list[asyncio.Task[None]] = []
    connection_id = uuid4()
    registered = False
    presence: PresenceObserver = app.state.presence
    try:
        await websocket.accept()
        presence.connect(campaign_id, guest.id, connection_id)
        registered = True
        heartbeat = Heartbeat()
        tasks.append(
            asyncio.create_task(
                _receive_loop(
                    websocket,
                    app,
                    campaign_id,
                    guest.id,
                    connection_id,
                    websocket.cookies.get(SESSION_COOKIE_NAME),
                    heartbeat,
                )
            )
        )
        tasks.append(
            asyncio.create_task(
                _pump(
                    websocket,
                    queue,
                    app,
                    campaign_id,
                    guest.id,
                    websocket.cookies.get(SESSION_COOKIE_NAME),
                )
            )
        )
        tasks.append(asyncio.create_task(_heartbeat(app, queue, heartbeat)))
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            with suppress(asyncio.CancelledError):
                await asyncio.gather(*tasks, return_exceptions=True)
        hub.unsubscribe(campaign_id, token)
        if registered:
            presence.disconnect(connection_id)


@router.get("/{campaign_id}/chat/events", response_model=ChatHistoryResponse)
def get_chat_history(
    campaign_id: UUID,
    guest: Guest,
    service: Service,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    after: AfterSequence = None,
) -> ChatHistoryResponse:
    """Return the member-only chronological chat stream snapshot."""
    try:
        history = service.get_history(campaign_id, guest.id, after_sequence=after)
    except NotAMember as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="forbidden",
        ) from error
    reader: GameSessionReader = request.app.state.game_session_reader_factory(session)
    queue_reader: QueueReader = request.app.state.queue_reader_factory(session)
    presence: PresenceReader = request.app.state.presence
    return ChatHistoryResponse.model_validate(
        {
            "campaign_id": campaign_id,
            "events": [event_to_wire(event) for event in history.events],
            "last_sequence": history.last_sequence,
            "game_session_state": asdict(reader.read(campaign_id)),
            "presence_state": asdict(presence.read(campaign_id)),
            "queue_state": asdict(queue_reader.read(campaign_id)),
        }
    )


__all__ = ["router"]

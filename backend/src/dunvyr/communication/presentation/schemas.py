"""Pydantic DTOs for the communication REST/WebSocket boundary."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ChatMessageBody(BaseModel):
    id: UUID
    author_id: UUID
    author_nickname: str
    client_message_id: UUID
    content: str
    created_at: datetime


class ChatMemberBody(BaseModel):
    guest_id: UUID
    nickname: str
    role: str
    joined_at: datetime


class ChatMessageEventResponse(BaseModel):
    type: Literal["message"]
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    message: ChatMessageBody


class ChatMemberJoinedEventResponse(BaseModel):
    type: Literal["member_joined"]
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    member: ChatMemberBody


class GameSessionBody(BaseModel):
    id: UUID
    status: Literal["running", "paused", "ended"]
    started_at: datetime
    ended_at: datetime | None


class GameSessionStateBody(BaseModel):
    revision: int
    session: GameSessionBody | None


class PresenceStateBody(BaseModel):
    epoch: UUID
    revision: int
    online_guest_ids: tuple[UUID, ...]


class GameSessionEventResponse(BaseModel):
    type: Literal["game_session_changed"]
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    game_session_state: GameSessionStateBody


class QueueParticipantBody(BaseModel):
    guest_id: UUID
    character_id: UUID


class QueueBody(BaseModel):
    encounter_id: str
    participants: tuple[QueueParticipantBody, ...]
    round_order: tuple[UUID, ...]
    round_number: int
    cursor: int
    skipped: tuple[UUID, ...]
    current_guest_id: UUID | None


class QueueStateBody(BaseModel):
    version: int
    queue: QueueBody | None


class QueueEventResponse(BaseModel):
    type: Literal["queue_changed"]
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    queue_state: QueueStateBody


class CheckResultBody(BaseModel):
    dice: tuple[int, ...]
    characteristic: int
    skill: int
    modifier: int
    difficulty: int
    total: int
    success: bool


class CheckEventResponse(BaseModel):
    type: Literal["check_resolved"]
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    result: CheckResultBody


class NarrationBody(BaseModel):
    result_event_id: UUID
    state: Literal["pending", "generating", "ready", "failed"]
    revision: int
    text: str | None
    error: str | None


class NarrationEventResponse(BaseModel):
    type: Literal["narration_changed"]
    event_id: UUID
    campaign_id: UUID
    sequence: int
    occurred_at: datetime
    narration: NarrationBody


ChatEventResponse = Annotated[
    ChatMessageEventResponse
    | ChatMemberJoinedEventResponse
    | GameSessionEventResponse
    | QueueEventResponse
    | CheckEventResponse
    | NarrationEventResponse,
    Field(discriminator="type"),
]


class ChatHistoryResponse(BaseModel):
    campaign_id: UUID
    events: list[ChatEventResponse]
    last_sequence: int
    game_session_state: GameSessionStateBody
    presence_state: PresenceStateBody
    queue_state: QueueStateBody
    narrations: list[NarrationBody] = []
    narration_events: list[NarrationEventResponse] = []


__all__ = [
    "ChatEventResponse",
    "ChatHistoryResponse",
    "ChatMemberBody",
    "ChatMemberJoinedEventResponse",
    "ChatMessageBody",
    "ChatMessageEventResponse",
]

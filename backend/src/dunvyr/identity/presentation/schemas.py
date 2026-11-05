"""Pydantic DTOs for the identity REST boundary."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel


class CreateSessionRequest(BaseModel):
    nickname: str


class GuestResponse(BaseModel):
    id: UUID
    nickname: str

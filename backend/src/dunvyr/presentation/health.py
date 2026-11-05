"""Health endpoint proving the HTTP boundary and the database wiring are alive."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from dunvyr.infrastructure.db import get_session

router = APIRouter()


@router.get("/health")
def health(session: Annotated[Session, Depends(get_session)]) -> dict[str, str]:
    """Report liveness, checking the database with a real query."""
    session.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok"}

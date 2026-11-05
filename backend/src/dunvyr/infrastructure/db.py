"""SQLAlchemy engine and session infrastructure shared by the modular monolith."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

DEFAULT_DATABASE_URL = "sqlite:///./dunvyr.db"


def is_in_memory_sqlite_url(database_url: str) -> bool:
    """Return whether the URL points at a transient SQLite in-memory database."""
    if not database_url.startswith("sqlite"):
        return False
    if ":memory:" in database_url:
        return True
    # "sqlite://" and "sqlite+pysqlite://" with an empty path are in-memory.
    return database_url.split("://", 1)[-1].strip("/") == ""


def create_db_engine(database_url: str = DEFAULT_DATABASE_URL) -> Engine:
    """Create the SQLAlchemy engine for a database URL.

    SQLite connections always enforce foreign keys; file-based databases also
    switch to WAL journaling (a no-op for in-memory databases). In-memory
    databases use a shared StaticPool so migrations and the app see one schema.
    """
    if not database_url.startswith("sqlite"):
        return create_engine(database_url)

    in_memory = is_in_memory_sqlite_url(database_url)
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool if in_memory else None,
    )

    def _set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            if not in_memory:
                cursor.execute("PRAGMA journal_mode=WAL")
        finally:
            cursor.close()

    event.listen(engine, "connect", _set_sqlite_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    """Create a session factory bound to a single engine."""
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_session(request: Request) -> Iterator[Session]:
    """FastAPI dependency yielding a short-lived session from the app state."""
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session

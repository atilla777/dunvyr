"""Helpers shared by integration tests (kept out of conftest for direct import)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from starlette.testclient import WebSocketTestSession

BACKEND_DIR = Path(__file__).resolve().parents[2]
IN_MEMORY_URL = "sqlite+pysqlite:///:memory:"


def receive_non_presence(socket: WebSocketTestSession) -> dict[str, Any]:
    """Keep chat assertions about chat while presence shares the same socket."""
    while True:
        frame = socket.receive_json()
        if frame.get("type") == "ping":
            socket.send_json({"type": "pong", "nonce": frame["nonce"]})
        elif frame.get("type") != "presence_state":
            return cast(dict[str, Any], frame)


def alembic_config(engine: Engine) -> Config:
    """Build an Alembic config that migrates the injected engine, not a URL."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["engine"] = engine
    return config


def apply_migrations(engine: Engine) -> None:
    """Upgrade the injected engine to head using the real Alembic pipeline."""
    command.upgrade(alembic_config(engine), "head")

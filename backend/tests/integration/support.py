"""Helpers shared by integration tests (kept out of conftest for direct import)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

BACKEND_DIR = Path(__file__).resolve().parents[2]
IN_MEMORY_URL = "sqlite+pysqlite:///:memory:"


def alembic_config(engine: Engine) -> Config:
    """Build an Alembic config that migrates the injected engine, not a URL."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["engine"] = engine
    return config


def apply_migrations(engine: Engine) -> None:
    """Upgrade the injected engine to head using the real Alembic pipeline."""
    command.upgrade(alembic_config(engine), "head")

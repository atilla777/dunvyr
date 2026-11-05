"""Run Alembic migrations against an already-created application engine."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

DEFAULT_MIGRATIONS_DIR = "migrations"


def resolve_migrations_dir(raw: str | None) -> Path:
    directory = Path(raw or DEFAULT_MIGRATIONS_DIR)
    if not directory.is_absolute():
        directory = Path.cwd() / directory
    return directory


def run_migrations(engine: Engine, migrations_dir: str | None = None) -> None:
    """Upgrade the given engine to head using the project Alembic pipeline."""
    script_location = resolve_migrations_dir(migrations_dir)
    if not (script_location / "env.py").is_file():
        raise RuntimeError(f"Alembic migrations directory not found: {script_location}")

    config = Config()
    config.set_main_option("script_location", str(script_location))
    config.attributes["engine"] = engine
    command.upgrade(config, "head")

"""Alembic environment for the Dunvyr backend.

The target URL comes from an engine injected via ``config.attributes["engine"]``
(used by the in-memory SQLite test pipeline), then the ``sqlalchemy.url`` ini
option, then ``DUNVYR_DATABASE_URL``, then the local SQLite default.
"""

from __future__ import annotations

import os
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import Connection, create_engine

from dunvyr.infrastructure.db import DEFAULT_DATABASE_URL

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata: Any = None


def _configured_url() -> str:
    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url
    return os.environ.get("DUNVYR_DATABASE_URL", DEFAULT_DATABASE_URL)


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Run migrations without a live database connection."""
    context.configure(
        url=_configured_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against an injected engine or a URL-built engine."""
    injected_engine = config.attributes.get("engine")
    if injected_engine is not None:
        with injected_engine.begin() as connection:
            _run_migrations(connection)
        return

    injected_connection = config.attributes.get("connection")
    if injected_connection is not None:
        _run_migrations(injected_connection)
        return

    engine = create_engine(_configured_url())
    try:
        with engine.begin() as connection:
            _run_migrations(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

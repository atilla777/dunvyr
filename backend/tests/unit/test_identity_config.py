"""Unit tests for identity HTTP-boundary configuration helpers."""

from __future__ import annotations

import pytest

from dunvyr.identity.presentation.config import (
    DEFAULT_ALLOWED_ORIGINS,
    SESSION_COOKIE_NAME,
    AllowedOrigins,
    env_flag,
)


@pytest.mark.unit
def test_allowed_origins_default_to_local_vite_origins() -> None:
    assert DEFAULT_ALLOWED_ORIGINS == (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    assert AllowedOrigins.parse(None).origins == DEFAULT_ALLOWED_ORIGINS


@pytest.mark.unit
def test_allowed_origins_parse_comma_separated_values_and_trim_whitespace() -> None:
    allowed = AllowedOrigins.parse(" http://127.0.0.1:5273 , http://192.168.1.10:5273 ,, ")

    assert allowed.origins == (
        "http://127.0.0.1:5273",
        "http://192.168.1.10:5273",
    )
    assert allowed.contains("http://127.0.0.1:5273")
    assert not allowed.contains("http://127.0.0.1:9999")


@pytest.mark.unit
def test_allowed_origins_do_not_match_by_prefix() -> None:
    allowed = AllowedOrigins.parse("http://localhost:5173")

    assert not allowed.contains("http://localhost:5173.evil.example")


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "on"])
def test_env_flag_accepts_explicit_truthy_values(raw: str) -> None:
    assert env_flag(raw)


@pytest.mark.unit
@pytest.mark.parametrize("raw", [None, "", "0", "false", "off"])
def test_env_flag_rejects_other_values(raw: str | None) -> None:
    assert not env_flag(raw)


@pytest.mark.unit
def test_session_cookie_name_is_fixed() -> None:
    assert SESSION_COOKIE_NAME == "dunvyr_session"

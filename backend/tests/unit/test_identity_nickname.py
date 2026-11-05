"""Unit tests for the nickname value object (identity domain)."""

from __future__ import annotations

import pytest

from dunvyr.identity.domain.nickname import InvalidNickname, Nickname


@pytest.mark.unit
def test_parse_trims_leading_and_trailing_whitespace() -> None:
    nickname = Nickname.parse("  \tAlice \n ")

    assert nickname.value == "Alice"


@pytest.mark.unit
@pytest.mark.parametrize("raw", ["A", "я", "😀", "Alice-42", "x" * 32])
def test_parse_accepts_one_to_32_unicode_characters(raw: str) -> None:
    assert Nickname.parse(raw).value == raw


@pytest.mark.unit
def test_parse_counts_characters_not_bytes() -> None:
    assert Nickname.parse("😀" * 32).value == "😀" * 32


@pytest.mark.unit
@pytest.mark.parametrize(
    "raw",
    [
        "",
        "   ",
        "\t\n",
        "x" * 33,
        "Alice\x00",
        "Alice\nSecond",
        "\u200b" * 3,
    ],
)
def test_parse_rejects_invalid_nicknames(raw: str) -> None:
    with pytest.raises(InvalidNickname):
        Nickname.parse(raw)


@pytest.mark.unit
def test_parse_rejects_non_string_input() -> None:
    with pytest.raises(InvalidNickname):
        Nickname.parse(42)


@pytest.mark.unit
def test_direct_construction_requires_canonical_value() -> None:
    with pytest.raises(InvalidNickname):
        Nickname(" Alice ")

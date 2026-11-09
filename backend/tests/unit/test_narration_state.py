"""State changes are conditional on the current revision and attempt token."""

import pytest

import dunvyr.communication.domain as domain

pytestmark = pytest.mark.unit


def test_late_completion_cannot_override_a_new_attempt():
    complete = getattr(domain, "can_complete_narration", lambda *_: None)
    assert complete("generating", 3, "current", 3, "current") is True
    assert complete("generating", 3, "current", 3, "stale") is False
    assert complete("ready", 3, "current", 3, "current") is False
    assert complete("generating", 4, "current", 3, "current") is False


def test_ready_is_terminal_and_retry_requires_failed_cooldown_and_revision():
    retry = getattr(domain, "can_retry_narration", lambda *_: None)
    assert retry("failed", 3, 3, 10) is True
    assert retry("failed", 3, 2, 10) is False
    assert retry("failed", 3, 3, 9.99) is False
    for state in ("pending", "generating", "ready"):
        assert retry(state, 3, 3, 20) is False

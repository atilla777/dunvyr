"""Game session transitions are separate from the durable campaign."""

from importlib import import_module
from uuid import uuid4

import pytest


@pytest.mark.unit
def test_session_lifecycle() -> None:
    domain = import_module("dunvyr.campaigns.domain")
    factory = getattr(domain, "GameSession", None)
    assert factory is not None, "campaigns must provide a game session aggregate"
    session = factory.start(id=uuid4(), campaign_id=uuid4())
    assert session.status.value == "running"
    paused = session.transition("pause")
    assert paused.status.value == "paused"
    assert paused.transition("resume").status.value == "running"
    assert paused.transition("end").status.value == "ended"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("status", "action", "expected"),
    [
        ("running", "pause", "paused"),
        ("running", "end", "ended"),
        ("paused", "resume", "running"),
        ("paused", "end", "ended"),
        ("running", "resume", None),
        ("paused", "pause", None),
        ("ended", "pause", None),
        ("ended", "resume", None),
        ("ended", "end", None),
        ("running", "start", None),
    ],
)
def test_transition_matrix(status: str, action: str, expected: str | None) -> None:
    domain = import_module("dunvyr.campaigns.domain")
    factory = getattr(domain, "GameSession", None)
    assert factory is not None, "campaigns must provide a game session aggregate"
    session = factory.start(id=uuid4(), campaign_id=uuid4())
    if status == "paused":
        session = session.transition("pause")
    elif status == "ended":
        session = session.transition("end")
    if expected is None:
        with pytest.raises(ValueError):
            session.transition(action)
    else:
        result = session.transition(action)
        assert result.status.value == expected
        assert (result.id, result.campaign_id) == (session.id, session.campaign_id)
        assert session.status.value == status

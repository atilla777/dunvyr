"""Terminal confirmation cannot be repeated or normalized into another round."""

import pytest

from dunvyr.gameplay.domain import ProposalCollection, start_queue

pytestmark = pytest.mark.unit


def test_confirm_once_and_completed_queue_stays_terminal() -> None:
    collection = ProposalCollection("alice").create(
        proposal_id="p",
        actor="alice",
        character_id="c",
        encounter_id="e",
        object_id="o",
        solution_id="s",
        fingerprint="f",
    )
    queue = start_queue((("alice", "c"), ("bob", "d")))
    assert callable(getattr(collection, "confirm", None)), "confirmation transition required"
    assert callable(getattr(queue, "complete", None)), "terminal queue transition required"
    confirmed = collection.confirm("p", "alice", "alice")
    completed = queue.complete("alice")
    assert not confirmed.pending
    assert completed.current is None
    assert completed.normalize({"alice", "bob"}) == completed
    with pytest.raises(ValueError):
        confirmed.confirm("p", "alice", "alice")
    with pytest.raises(ValueError):
        completed.complete("alice")


def test_rejected_confirmation_does_not_consume_action() -> None:
    collection = ProposalCollection("alice").create(
        proposal_id="p",
        actor="alice",
        character_id="c",
        encounter_id="e",
        object_id="o",
        solution_id="s",
        fingerprint="f",
    )
    queue = start_queue((("alice", "c"),))
    assert callable(getattr(collection, "confirm", None))
    assert callable(getattr(queue, "complete", None))
    with pytest.raises(ValueError):
        collection.confirm("p", "alice", "bob")
    with pytest.raises(ValueError):
        queue.complete("bob")
    assert len(collection.pending) == 1
    assert queue.current == "alice"

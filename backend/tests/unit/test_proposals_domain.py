import pytest

from dunvyr.gameplay import domain

pytestmark = pytest.mark.unit


def test_collection_accepts_identical_intent_and_limits_pending_to_twenty() -> None:
    collection_type = getattr(domain, "ProposalCollection", None)
    assert collection_type is not None, "owner proposal collection must exist"
    collection = collection_type(owner="guest")
    for index in range(20):
        collection = collection.create(
            proposal_id=str(index),
            actor="guest",
            character_id="character",
            encounter_id="encounter",
            object_id="object",
            solution_id="solution",
            fingerprint="package",
        )
    assert len(collection.pending) == 20
    assert collection.version == 20
    with pytest.raises(ValueError):
        collection.create(
            proposal_id="extra",
            actor="guest",
            character_id="character",
            encounter_id="encounter",
            object_id="object",
            solution_id="solution",
            fingerprint="package",
        )


def test_owner_turn_is_required_to_edit_or_cancel_and_cancel_is_final() -> None:
    collection = domain.ProposalCollection(owner="guest").create(
        proposal_id="p",
        actor="guest",
        character_id="character",
        encounter_id="encounter",
        object_id="object",
        solution_id="solution",
        fingerprint="package",
    )
    edit = getattr(collection, "edit", None)
    cancel = getattr(collection, "cancel", None)
    assert callable(edit) and callable(cancel), "editing and cancellation must be supported"
    with pytest.raises(ValueError):
        edit("p", "other", "guest", "character", "e2", "o2", "s2", "package")
    with pytest.raises(ValueError):
        cancel("p", "guest", "other")
    edited = edit("p", "guest", "guest", "character", "e2", "o2", "s2", "package")
    assert collection.pending[0].solution_id == "solution"
    assert edited.pending[0].solution_id == "s2"
    cancelled = edited.cancel("p", "guest", "guest")
    assert cancelled.pending == ()
    assert cancelled.version == 3
    with pytest.raises(ValueError):
        cancelled.cancel("p", "guest", "guest")
    with pytest.raises(ValueError):
        cancelled.edit("p", "guest", "guest", "character", "e", "o", "s", "package")


def test_creation_rejects_foreign_actor_and_edit_rejects_other_character() -> None:
    collection = domain.ProposalCollection(owner="guest")
    create = dict(
        proposal_id="p",
        character_id="character",
        encounter_id="e",
        object_id="o",
        solution_id="s",
        fingerprint="package",
    )
    with pytest.raises(ValueError):
        collection.create(actor="other", **create)
    collection = collection.create(actor="guest", **create)
    with pytest.raises(ValueError):
        collection.edit("p", "guest", "guest", "other-character", "e", "o", "s", "package")
    assert collection.version == 1


def test_cancelled_proposal_releases_capacity_but_id_cannot_be_reused() -> None:
    collection = domain.ProposalCollection(owner="guest")
    values = dict(
        character_id="c", encounter_id="e", object_id="o", solution_id="s", fingerprint="f"
    )
    for index in range(20):
        collection = collection.create(proposal_id=str(index), actor="guest", **values)
    collection = collection.cancel("0", "guest", "guest")
    with pytest.raises(ValueError):
        collection.create(proposal_id="0", actor="guest", **values)
    collection = collection.create(proposal_id="new", actor="guest", **values)
    assert len(collection.pending) == 20
    assert collection.version == 22

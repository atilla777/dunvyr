import pytest

from dunvyr.gameplay import domain

pytestmark = pytest.mark.unit


def test_start_preserves_roster_and_starts_first_round() -> None:
    start = getattr(domain, "start_queue", None)
    assert callable(start), "starting a queue must be supported"
    queue = start((("a", "ca"), ("b", "cb")))
    assert queue.base_order == (("a", "ca"), ("b", "cb"))
    assert queue.round_order == ("a", "b")
    assert queue.round_number == 1
    assert queue.current == "a"


@pytest.mark.parametrize(
    "participants",
    [
        (),
        (("", "c"),),
        (("a", ""),),
        (("a", "c"), ("a", "d")),
        (("a", "c"), ("b", "c")),
        ((" ", "c"),),
    ],
)
def test_invalid_roster_is_rejected(participants: tuple[tuple[str, str], ...]) -> None:
    with pytest.raises(ValueError):
        domain.start_queue(participants)


def test_normalize_offline_and_reconnect_does_not_restore_skipped_slots() -> None:
    queue = domain.start_queue((("a", "ca"), ("b", "cb"), ("c", "cc")))
    normalize = getattr(queue, "normalize", None)
    assert callable(normalize), "offline participants must be skipped"
    after = normalize({"c"})
    assert (after.cursor, after.skipped, after.current, after.version) == (2, ("a", "b"), "c", 2)
    assert after.normalize({"a", "c"}) == after
    assert queue.cursor == 0


def test_all_offline_waits_then_reconnect_advances_once() -> None:
    queue = domain.start_queue((("a", "ca"), ("b", "cb")))
    normalize = getattr(queue, "normalize", None)
    assert callable(normalize), "offline participants must be skipped"
    waiting = normalize(set())
    assert (
        waiting.round_number,
        waiting.cursor,
        waiting.skipped,
        waiting.current,
        waiting.version,
    ) == (1, 2, ("a", "b"), None, 2)
    assert waiting.normalize(set()) == waiting
    resumed = waiting.normalize({"b"})
    assert (
        resumed.round_number,
        resumed.cursor,
        resumed.skipped,
        resumed.current,
        resumed.version,
    ) == (2, 1, ("a",), "b", 3)


def test_swap_changes_only_current_round_order_without_consuming() -> None:
    queue = domain.start_queue((("a", "ca"), ("b", "cb"), ("c", "cc")))
    swap = getattr(queue, "swap", None)
    assert callable(swap), "active player must be able to swap"
    swapped = swap("a", "c", {"a", "b", "c"})
    assert (
        swapped.round_order,
        swapped.current,
        swapped.cursor,
        swapped.skipped,
        swapped.version,
    ) == (("c", "b", "a"), "c", 0, (), 2)
    waiting = swapped.normalize(set())
    resumed = waiting.normalize({"a", "b", "c"})
    assert (resumed.round_number, resumed.round_order, resumed.current) == (2, ("a", "b", "c"), "a")


@pytest.mark.parametrize(
    "actor,target,online",
    [
        ("b", "c", {"a", "b", "c"}),
        ("x", "b", {"a", "b"}),
        ("a", "a", {"a", "b"}),
        ("a", "x", {"a", "x"}),
        ("a", "b", {"a"}),
        ("a", "b", {"b"}),
    ],
)
def test_invalid_swaps_are_rejected(actor: str, target: str, online: set[str]) -> None:
    queue = domain.start_queue((("a", "ca"), ("b", "cb"), ("c", "cc")))
    swap = getattr(queue, "swap", None)
    assert callable(swap), "swap validation must be supported"
    with pytest.raises(ValueError):
        swap(actor, target, online)


def test_swap_rejects_already_skipped_target() -> None:
    queue = domain.start_queue((("a", "ca"), ("b", "cb"))).normalize({"b"})
    swap = getattr(queue, "swap", None)
    assert callable(swap), "swap validation must be supported"
    with pytest.raises(ValueError):
        swap("b", "a", {"a", "b"})


@pytest.mark.parametrize(
    "online,cursor,skipped,current",
    [
        ({"a", "c"}, 0, (), "a"),
        ({"b"}, 1, ("a",), "b"),
        ({"c"}, 2, ("a", "b"), "c"),
        ({"outsider"}, 3, ("a", "b", "c"), None),
    ],
)
def test_normalize_sequences(
    online: set[str], cursor: int, skipped: tuple[str, ...], current: str | None
) -> None:
    queue = domain.start_queue((("a", "ca"), ("b", "cb"), ("c", "cc")))
    result = queue.normalize(online)
    assert (result.round_number, result.cursor, result.skipped, result.current) == (
        1,
        cursor,
        skipped,
        current,
    )
    assert result.version == (1 if cursor == 0 else 2)
    assert result.normalize(online) == result

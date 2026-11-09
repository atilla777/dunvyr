"""The bounded noncombat-v1 arithmetic, independent of the random source."""

from itertools import product

import pytest

from dunvyr.gameplay import domain

pytestmark = pytest.mark.unit


def test_noncombat_check_threshold_and_all_dice() -> None:
    resolve = getattr(domain, "resolve_noncombat_check", None)
    assert callable(resolve), "gameplay must resolve the bounded noncombat check"
    for dice in product((-1, 0, 1), repeat=4):
        for base in (4, 5, 6):
            result = resolve(base, 0, dice)
            assert result.total == base + sum(dice)
            assert result.success is (result.total >= 5)
            assert result.dice == dice
            assert result.modifier == 0


@pytest.mark.parametrize("dice", [(), (0, 0, 0), (0, 0, 0, 0, 0), (0, 0, 0, 2), (0, 0, 0, True)])
def test_noncombat_check_rejects_malformed_dice(dice: tuple[int, ...]) -> None:
    resolve = getattr(domain, "resolve_noncombat_check", None)
    assert callable(resolve), "gameplay must resolve the bounded noncombat check"
    with pytest.raises(ValueError):
        resolve(2, 1, dice)

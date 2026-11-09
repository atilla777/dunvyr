"""Authored success and failure update only their declared effects."""

import json
from pathlib import Path

import pytest

from dunvyr.adventures.domain import package as domain

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("success", [True, False])
def test_authored_branch_changes_goal_scene_and_availability(success: bool) -> None:
    package = json.loads(
        (Path(__file__).parents[3] / "adventures/last-shift/adventure.json").read_text()
    )
    apply = getattr(domain, "apply_check_outcome", None)
    assert callable(apply), "adventure progression participant required"
    progression = apply(package, {}, "terminal-diagnostics", "terminal", "repair-terminal", success)
    assert progression["facts"]["terminal-inspected"] is True
    assert progression["facts"]["terminal-stable"] is success
    assert "остальн" in progression["goal"] if success else "Продолжить" in progression["goal"]
    assert progression["objects"]["terminal"] != "Экран терминала ещё светится."
    with pytest.raises(ValueError):
        apply(package, progression, "terminal-diagnostics", "terminal", "repair-terminal", success)


def test_applied_public_outcome_contains_only_changed_visible_scene_data():
    package = json.loads(
        (Path(__file__).parents[3] / "adventures/last-shift/adventure.json").read_text()
    )
    project = getattr(domain, "project_applied_public_outcome", lambda *_: None)
    result = project(
        package,
        {},
        {
            "facts": {"secret": True},
            "objects": {"terminal": "Новый экран", "hidden-object": "Секрет"},
            "goal": "Цель",
        },
    )
    assert result == (("object_description", "Новый экран"), ("goal", "Цель"))

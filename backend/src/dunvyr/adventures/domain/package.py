"""Semantic rules for a structurally validated adventure package."""

from typing import Any


def _unique(items: list[dict[str, Any]], label: str) -> set[str]:
    ids = [item["id"] for item in items]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate {label} ID")
    return set(ids)


def validate_references(package: dict[str, Any]) -> None:
    skill_ids = _unique(package["skills"], "skill")
    _unique(package["archetypes"], "archetype")
    locations = package["locations"]
    location_ids = _unique(locations, "location")
    asset_ids = _unique(package["assets"], "asset")
    if package["initial_location_id"] not in location_ids:
        raise ValueError("missing initial location")
    for archetype in package["archetypes"]:
        if not set(archetype["skills"]) <= skill_ids:
            raise ValueError(f"unknown skill in archetype {archetype['id']}")
    object_ids: set[str] = set()
    exit_ids: set[str] = set()
    for location in locations:
        if location["illustration"] not in asset_ids:
            raise ValueError(f"unknown illustration asset in {location['id']}")
        local_objects = _unique(location["objects"], "object")
        local_exits = _unique(location["exits"], "exit")
        if object_ids & local_objects or exit_ids & local_exits:
            raise ValueError("duplicate object or exit ID")
        object_ids.update(local_objects)
        exit_ids.update(local_exits)
        for exit_ in location["exits"]:
            if (
                exit_["target_location_id"] not in location_ids
                or exit_["object_id"] not in local_objects
            ):
                raise ValueError(f"invalid exit reference in {location['id']}")

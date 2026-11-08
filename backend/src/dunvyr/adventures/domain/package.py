"""Semantic rules for a structurally validated adventure package."""

from typing import Any


def project_initial_map(package: dict[str, Any]) -> dict[str, Any]:
    """Expose explicit knowledge only; unknown targets never carry identity."""
    initial = package["initial_location_id"]
    knowledge = package["initial_knowledge"] if package["schema_version"] == 2 else {}
    known_locations = {initial, *knowledge.get("discovered_location_ids", [])}
    known_exits = set(knowledge.get("known_exit_ids", []))
    locations = []
    exits = []
    for location in package["locations"]:
        if location["id"] not in known_locations:
            continue
        locations.append(
            {
                "id": location["id"],
                "name": location["name"],
                "state": "visited" if location["id"] == initial else "discovered",
            }
        )
        labels = {
            obj["id"]: obj["name"] for obj in location["objects"] if obj["visibility"] == "visible"
        }
        for exit_ in location["exits"]:
            if exit_["id"] in known_exits:
                exits.append(
                    {
                        "source_location_id": location["id"],
                        "label": labels[exit_["object_id"]],
                        "target_location_id": exit_["target_location_id"]
                        if exit_["target_location_id"] in known_locations
                        else None,
                    }
                )
    return {"current_location_id": initial, "locations": locations, "exits": exits}


def project_initial_scene(package: dict[str, Any]) -> dict[str, Any]:
    """Project only public fields from the pinned initial location."""
    locations = [loc for loc in package["locations"] if loc["id"] == package["initial_location_id"]]
    if len(locations) != 1:
        raise ValueError("invalid initial location")
    location = locations[0]
    return {
        "name": location["name"],
        "description": location["public_description"],
        "illustration": location["illustration"],
        "objects": [
            {
                "id": obj["id"],
                "name": obj["name"],
                "description": obj["public_description"],
                "hotspot": {key: obj["hotspot"][key] for key in ("x", "y", "width", "height")},
            }
            for obj in location["objects"]
            if obj["visibility"] == "visible"
        ],
    }


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
    if package["schema_version"] == 2:
        knowledge = package["initial_knowledge"]
        discovered = knowledge["discovered_location_ids"]
        known_exits = knowledge["known_exit_ids"]
        if (
            len(discovered) != len(set(discovered))
            or not set(discovered) <= location_ids
            or package["initial_location_id"] in discovered
        ):
            raise ValueError("invalid discovered locations")
        if len(known_exits) != len(set(known_exits)) or not set(known_exits) <= exit_ids:
            raise ValueError("invalid known exits")
        known_rooms = {package["initial_location_id"], *discovered}
        for location in locations:
            visible = {obj["id"] for obj in location["objects"] if obj["visibility"] == "visible"}
            for exit_ in location["exits"]:
                if exit_["id"] in known_exits and (
                    location["id"] not in known_rooms or exit_["object_id"] not in visible
                ):
                    raise ValueError("known exit has unknown source or hidden label")

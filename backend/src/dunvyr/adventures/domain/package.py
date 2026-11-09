"""Semantic rules for a structurally validated adventure package."""

from typing import Any


def project_initial_map(package: dict[str, Any]) -> dict[str, Any]:
    """Expose explicit knowledge only; unknown targets never carry identity."""
    initial = package["initial_location_id"]
    knowledge = package["initial_knowledge"] if package["schema_version"] in (2, 3) else {}
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


def project_initial_encounters(
    package: dict[str, Any], fingerprint: str, progression: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Project only currently obvious solutions; no outcome or condition data escapes."""
    result: dict[str, Any] = {
        "fingerprint": fingerprint,
        "current_location_id": package["initial_location_id"],
        "encounters": [],
    }
    if package["schema_version"] != 3:
        return result
    facts = {fact["id"]: fact["initial_value"] for fact in package["facts"]}
    facts.update((progression or {}).get("facts", {}))
    conditions = {condition["id"]: condition for condition in package["conditions"]}
    skills = {skill["id"]: skill for skill in package["skills"]}
    for encounter in package["encounters"]:
        solutions = []
        for solution in encounter["solutions"]:
            if not all(
                facts[conditions[id_]["fact_id"]] == conditions[id_]["expected"]
                for id_ in solution["condition_ids"]
            ):
                continue
            skill = skills[solution["check"]["skill_id"]]
            solutions.append(
                {
                    "id": solution["id"],
                    "name": solution["name"],
                    "description": solution["public_description"],
                    "check": {
                        "skill_id": skill["id"],
                        "skill_name": skill["name"],
                        "characteristic": skill["characteristic"],
                        "difficulty": solution["check"]["difficulty"],
                    },
                }
            )
        result["encounters"].append(
            {
                "id": encounter["id"],
                "object_id": encounter["object_id"],
                "name": encounter["name"],
                "description": encounter["public_description"],
                "solutions": solutions,
            }
        )
    return result


def apply_check_outcome(
    package: dict[str, Any],
    progression: dict[str, Any],
    encounter_id: str,
    object_id: str,
    solution_id: str,
    success: bool,
) -> dict[str, Any]:
    """Apply a currently available authored branch without exposing outcome identifiers."""
    catalog = project_initial_encounters(package, "", progression)
    available = any(
        e["id"] == encounter_id
        and e["object_id"] == object_id
        and any(s["id"] == solution_id for s in e["solutions"])
        for e in catalog["encounters"]
    )
    if not available:
        raise ValueError("selection unavailable")
    encounter = next(e for e in package["encounters"] if e["id"] == encounter_id)
    solution = next(s for s in encounter["solutions"] if s["id"] == solution_id)
    outcome_id = solution["success_outcome_id" if success else "failure_outcome_id"]
    effects = next(o["effects"] for o in package["outcomes"] if o["id"] == outcome_id)
    facts = {f["id"]: f["initial_value"] for f in package["facts"]}
    facts.update(progression.get("facts", {}))
    facts.update({f["fact_id"]: f["value"] for f in effects["set_facts"]})
    objects = dict(progression.get("objects", {}))
    objects.update({o["object_id"]: o["public_description"] for o in effects["object_updates"]})
    goal = effects["public_goal"] or progression.get("goal", package["initial_public_goal"])
    return {"facts": facts, "objects": objects, "goal": goal}


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
    if package["schema_version"] in (2, 3):
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
    if package["schema_version"] == 3:
        _validate_encounters(package, skill_ids)


def _validate_encounters(package: dict[str, Any], skill_ids: set[str]) -> None:
    facts = {fact["id"]: fact["initial_value"] for fact in package["facts"]}
    _unique(package["facts"], "fact")
    _unique(package["conditions"], "condition")
    outcome_ids = _unique(package["outcomes"], "outcome")
    _unique(package["encounters"], "encounter")
    conditions = {condition["id"]: condition for condition in package["conditions"]}
    if any(condition["fact_id"] not in facts for condition in conditions.values()):
        raise ValueError("unknown condition fact")
    initial = next(
        loc for loc in package["locations"] if loc["id"] == package["initial_location_id"]
    )
    visible = {obj["id"] for obj in initial["objects"] if obj["visibility"] == "visible"}
    for outcome in package["outcomes"]:
        effects = outcome["effects"]
        assigned = [item["fact_id"] for item in effects["set_facts"]]
        updated = [item["object_id"] for item in effects["object_updates"]]
        if len(assigned) != len(set(assigned)) or not set(assigned) <= facts.keys():
            raise ValueError("invalid fact assignments")
        if len(updated) != len(set(updated)) or not set(updated) <= visible:
            raise ValueError("invalid object updates")
    solution_ids: set[str] = set()
    available = False
    for encounter in package["encounters"]:
        if encounter["location_id"] != initial["id"] or encounter["object_id"] not in visible:
            raise ValueError("invalid encounter location or object")
        for solution in encounter["solutions"]:
            if solution["id"] in solution_ids:
                raise ValueError("duplicate solution ID")
            solution_ids.add(solution["id"])
            ids = solution["condition_ids"]
            if len(ids) != len(set(ids)) or not set(ids) <= conditions.keys():
                raise ValueError("invalid solution conditions")
            expected: dict[str, bool] = {}
            for id_ in ids:
                condition = conditions[id_]
                fact_id = condition["fact_id"]
                if fact_id in expected and expected[fact_id] != condition["expected"]:
                    raise ValueError("contradictory conditions")
                expected[fact_id] = condition["expected"]
            if solution["check"]["skill_id"] not in skill_ids:
                raise ValueError("unknown skill")
            success = solution["success_outcome_id"]
            failure = solution["failure_outcome_id"]
            if success == failure or not {success, failure} <= outcome_ids:
                raise ValueError("invalid outcomes")
            available |= all(facts[id_] == value for id_, value in expected.items())
    if not available:
        raise ValueError("no initially available solution")

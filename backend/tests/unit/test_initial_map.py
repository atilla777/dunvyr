"""Initial map is an allowlist, not a traversal of the source graph."""

import copy
import json
from pathlib import Path

import pytest

from dunvyr.adventures.domain import package as domain


@pytest.mark.unit
def test_v3_map_preserves_v2_initial_knowledge_and_validation():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    data = json.loads(path.read_text())
    data["schema_version"] = 3
    data["initial_knowledge"]["discovered_location_ids"] = ["vault"]
    assert any(
        location["id"] == "vault" for location in domain.project_initial_map(data)["locations"]
    )
    data["initial_knowledge"]["discovered_location_ids"] = ["missing"]
    with pytest.raises(ValueError, match="invalid discovered locations"):
        domain.validate_references(data)


@pytest.mark.unit
def test_initial_map_does_not_follow_known_exits_or_reveal_hidden_destinations():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    data = json.loads(path.read_text())
    room = data["locations"][0]
    data["locations"] = [room]
    hidden = copy.deepcopy(room)
    hidden.update(id="secret-room", name="Secret name", illustration="secret-asset")
    hidden["objects"] = []
    hidden["exits"] = []
    room["exits"] = [
        {
            "id": "secret-exit-one",
            "object_id": room["objects"][0]["id"],
            "target_location_id": "secret-room",
        },
        {
            "id": "secret-exit-two",
            "object_id": room["objects"][0]["id"],
            "target_location_id": "secret-room",
        },
    ]
    room["objects"][0]["visibility"] = "visible"
    data["locations"].append(hidden)
    data["schema_version"] = 2
    data["initial_knowledge"] = {
        "discovered_location_ids": [],
        "known_exit_ids": ["secret-exit-one", "secret-exit-two"],
    }
    project = getattr(domain, "project_initial_map", None)
    assert callable(project), "the domain must expose an initial-map projection"
    result = project(data)
    assert result["locations"] == [{"id": room["id"], "name": room["name"], "state": "visited"}]
    assert len(result["exits"]) == 2
    assert all(exit_["target_location_id"] is None for exit_ in result["exits"])
    serialized = json.dumps(result)
    for secret in ("secret-room", "Secret name", "secret-asset", "secret-exit"):
        assert secret not in serialized


@pytest.mark.unit
def test_initial_knowledge_rejects_unknown_or_duplicate_references_and_hidden_labels():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    data = json.loads(path.read_text())
    room = data["locations"][0]
    data["locations"] = [room]
    obj = room["objects"][0]
    room["exits"] = [{"id": "known-exit", "object_id": obj["id"], "target_location_id": room["id"]}]
    data["schema_version"] = 2
    data["initial_knowledge"] = {"discovered_location_ids": [], "known_exit_ids": ["known-exit"]}
    obj["visibility"] = "hidden"
    with pytest.raises(ValueError):
        domain.validate_references(data)
    obj["visibility"] = "visible"
    for key, ids in (
        ("known_exit_ids", ["missing"]),
        ("known_exit_ids", ["known-exit", "known-exit"]),
        ("discovered_location_ids", ["missing"]),
        ("discovered_location_ids", [room["id"]]),
    ):
        invalid = copy.deepcopy(data)
        invalid["initial_knowledge"][key] = ids
        with pytest.raises(ValueError):
            domain.validate_references(invalid)


@pytest.mark.unit
def test_v1_ignores_graph_edges_and_only_knows_initial_room():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    data = json.loads(path.read_text())
    data["schema_version"] = 1
    data.pop("initial_knowledge")
    room = data["locations"][0]
    room["exits"] = [
        {"id": "edge", "object_id": room["objects"][0]["id"], "target_location_id": room["id"]}
    ]
    result = domain.project_initial_map(data)
    assert result["locations"] == [{"id": room["id"], "name": room["name"], "state": "visited"}]
    assert result["exits"] == []


@pytest.mark.unit
def test_v1_projection_never_interprets_v2_knowledge_even_if_present():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    data = json.loads(path.read_text())
    data["schema_version"] = 1
    result = domain.project_initial_map(data)
    assert [location["id"] for location in result["locations"]] == ["airlock"]
    assert result["exits"] == []


@pytest.mark.unit
def test_known_rooms_do_not_implicitly_disclose_outgoing_exits():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    data = json.loads(path.read_text())
    initial = data["locations"][0]
    data["locations"] = [initial]
    discovered = copy.deepcopy(initial)
    discovered.update(id="lobby", name="Lobby")
    data["locations"].append(discovered)
    data["schema_version"] = 2
    data["initial_knowledge"] = {"discovered_location_ids": ["lobby"], "known_exit_ids": []}
    initial["exits"] = [
        {
            "id": "hidden-edge",
            "object_id": initial["objects"][0]["id"],
            "target_location_id": "lobby",
        }
    ]
    result = domain.project_initial_map(data)
    assert result["locations"][1] == {"id": "lobby", "name": "Lobby", "state": "discovered"}
    assert result["exits"] == []


@pytest.mark.unit
def test_secret_graph_changes_do_not_change_projection():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    original = json.loads(path.read_text())
    changed = copy.deepcopy(original)
    secret = next(room for room in changed["locations"] if room["id"] == "vault")
    secret.update(
        name="SECRET NAME", public_description="SECRET DESCRIPTION", illustration="SECRET ASSET"
    )
    secret["objects"] = [
        {
            "id": "secret-object",
            "name": "SECRET LABEL",
            "visibility": "hidden",
            "hotspot": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
        }
    ]
    changed["locations"].insert(0, changed["locations"].pop())
    assert domain.project_initial_map(original) == domain.project_initial_map(changed)
    payload = json.dumps(domain.project_initial_map(changed), ensure_ascii=False)
    for value in ("vault", "service-bay", "SECRET", "airlock-secret", "hotspot"):
        assert value not in payload


@pytest.mark.unit
def test_known_exit_cannot_originate_from_an_unknown_room():
    path = Path(__file__).resolve().parents[3] / "adventures/last-shift/adventure.json"
    data = json.loads(path.read_text())
    room = next(room for room in data["locations"] if room["id"] == "vault")
    room["objects"] = [{"id": "vault-door", "name": "Door", "visibility": "visible"}]
    room["exits"] = [
        {"id": "vault-exit", "object_id": "vault-door", "target_location_id": "airlock"}
    ]
    data["initial_knowledge"]["known_exit_ids"].append("vault-exit")
    with pytest.raises(ValueError, match="unknown source"):
        domain.validate_references(data)

"""V3 template validation and the initial public allowlist."""

import base64
import copy
import gzip
import json
from dataclasses import FrozenInstanceError
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from dunvyr.adventures.domain import package as domain
from dunvyr.adventures.infrastructure.package_loader import load_package, parse_package
from dunvyr.adventures.infrastructure.snapshots import SqlSnapshotReader


@pytest.fixture
def v3():
    path = Path(__file__).resolve().parents[1] / "fixtures/last-shift-v2.json.gz.b64"
    data = json.loads(gzip.decompress(base64.b64decode(path.read_text())))
    data.update(
        schema_version=3,
        initial_public_goal="Goal",
        facts=[
            {"id": "inspected", "initial_value": False},
            {"id": "stable", "initial_value": False},
        ],
        conditions=[{"id": "uninspected", "fact_id": "inspected", "expected": False}],
        outcomes=[
            {
                "id": "success",
                "effects": {
                    "set_facts": [{"fact_id": "stable", "value": True}],
                    "object_updates": [],
                    "public_goal": None,
                },
            },
            {
                "id": "failure",
                "effects": {"set_facts": [], "object_updates": [], "public_goal": "Continue"},
            },
        ],
        encounters=[
            {
                "id": "diagnostics",
                "kind": "noncombat",
                "location_id": "airlock",
                "object_id": "terminal",
                "name": "Terminal",
                "public_description": "Inspect it",
                "solutions": [
                    {
                        "id": "repair-it",
                        "name": "Repair",
                        "public_description": "Check connections",
                        "visibility": "obvious",
                        "condition_ids": ["uninspected"],
                        "check": {"skill_id": "repair", "difficulty": 5},
                        "success_outcome_id": "success",
                        "failure_outcome_id": "failure",
                    }
                ],
            }
        ],
    )
    return data


@pytest.mark.unit
def test_v3_schema_and_safe_projection(v3):
    unavailable = copy.deepcopy(v3["encounters"][0]["solutions"][0])
    unavailable.update(id="secret-unavailable", name="SECRET")
    v3["conditions"].append({"id": "already", "fact_id": "inspected", "expected": True})
    unavailable["condition_ids"] = ["already"]
    v3["encounters"][0]["solutions"].append(unavailable)
    parsed = parse_package(v3).model_dump()
    projection = domain.project_initial_encounters(parsed, "fingerprint")
    assert projection == {
        "fingerprint": "fingerprint",
        "current_location_id": "airlock",
        "encounters": [
            {
                "id": "diagnostics",
                "object_id": "terminal",
                "name": "Terminal",
                "description": "Inspect it",
                "solutions": [
                    {
                        "id": "repair-it",
                        "name": "Repair",
                        "description": "Check connections",
                        "check": {
                            "skill_id": "repair",
                            "skill_name": "Ремонт",
                            "characteristic": "intellect",
                            "difficulty": 5,
                        },
                    }
                ],
            }
        ],
    }
    assert "secret-unavailable" not in json.dumps(projection)


@pytest.mark.unit
@pytest.mark.parametrize(
    "mutation",
    [
        "fact_bool",
        "expected_bool",
        "difficulty_bool",
        "difficulty_range",
        "override",
        "extra",
        "missing_goal",
        "duplicate_fact",
        "duplicate_condition",
        "duplicate_outcome",
        "duplicate_solution",
        "missing_fact",
        "missing_condition",
        "missing_skill",
        "missing_outcome",
        "same_outcome",
        "duplicate_assignment",
        "unknown_assignment",
        "duplicate_update",
        "duplicate_condition_ref",
        "contradictory",
        "unavailable",
        "hidden_object",
        "other_location",
        "update_hidden",
        "encounter_count",
    ],
)
def test_v3_rejects_invalid_structures_and_references(v3, mutation):
    sol = v3["encounters"][0]["solutions"][0]
    effects = v3["outcomes"][0]["effects"]
    if mutation == "fact_bool":
        v3["facts"][0]["initial_value"] = 0
    elif mutation == "expected_bool":
        v3["conditions"][0]["expected"] = 0
    elif mutation == "difficulty_bool":
        sol["check"]["difficulty"] = True
    elif mutation == "difficulty_range":
        sol["check"]["difficulty"] = 21
    elif mutation == "override":
        sol["check"]["characteristic"] = "strength"
    elif mutation == "extra":
        sol["effects"] = {}
    elif mutation == "missing_goal":
        del v3["initial_public_goal"]
    elif mutation == "duplicate_fact":
        v3["facts"].append(copy.deepcopy(v3["facts"][0]))
    elif mutation == "duplicate_condition":
        v3["conditions"].append(copy.deepcopy(v3["conditions"][0]))
    elif mutation == "duplicate_outcome":
        v3["outcomes"].append(copy.deepcopy(v3["outcomes"][0]))
    elif mutation == "duplicate_solution":
        v3["encounters"][0]["solutions"].append(copy.deepcopy(sol))
    elif mutation == "missing_fact":
        v3["conditions"][0]["fact_id"] = "missing"
    elif mutation == "missing_condition":
        sol["condition_ids"] = ["missing"]
    elif mutation == "missing_skill":
        sol["check"]["skill_id"] = "missing"
    elif mutation == "missing_outcome":
        sol["success_outcome_id"] = "missing"
    elif mutation == "same_outcome":
        sol["failure_outcome_id"] = "success"
    elif mutation == "duplicate_assignment":
        effects["set_facts"].append(copy.deepcopy(effects["set_facts"][0]))
    elif mutation == "unknown_assignment":
        effects["set_facts"][0]["fact_id"] = "missing"
    elif mutation == "duplicate_update":
        effects["object_updates"] = [{"object_id": "terminal", "public_description": "x"}] * 2
    elif mutation == "duplicate_condition_ref":
        sol["condition_ids"] *= 2
    elif mutation == "contradictory":
        v3["conditions"].append({"id": "opposite", "fact_id": "inspected", "expected": True})
        sol["condition_ids"].append("opposite")
    elif mutation == "unavailable":
        v3["conditions"][0]["expected"] = True
    elif mutation == "hidden_object":
        obj = copy.deepcopy(v3["locations"][0]["objects"][0])
        obj.update(id="hidden-object", visibility="hidden")
        v3["locations"][0]["objects"].append(obj)
        v3["encounters"][0]["object_id"] = "hidden-object"
    elif mutation == "other_location":
        v3["encounters"][0]["location_id"] = "vault"
    elif mutation == "update_hidden":
        obj = copy.deepcopy(v3["locations"][0]["objects"][0])
        obj.update(id="hidden-object", visibility="hidden")
        v3["locations"][0]["objects"].append(obj)
        effects["object_updates"] = [{"object_id": "hidden-object", "public_description": "x"}]
    elif mutation == "encounter_count":
        v3["encounters"] = []
    with pytest.raises(ValueError):
        parse_package(v3)


@pytest.mark.unit
def test_pinned_reader_v3_catalog_and_templates_are_immutable(v3):
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE adventures_snapshots "
                "(campaign_id TEXT, content TEXT, fingerprint TEXT)"
            )
        )
    campaign_id = uuid4()
    with Session(engine) as session:
        reader = SqlSnapshotReader(session)
        assert reader.available_encounters(campaign_id) is None
        session.execute(
            text("INSERT INTO adventures_snapshots VALUES (:id, :content, :fp)"),
            {
                "id": str(campaign_id),
                "content": json.dumps(v3),
                "fp": "pinned",
            },
        )
        catalog = reader.available_encounters(campaign_id)
        assert catalog is not None and catalog.fingerprint == "pinned"
        assert catalog.encounters[0].solutions[0].check.characteristic == "intellect"
        assert isinstance(catalog.encounters, tuple)
        assert isinstance(catalog.encounters[0].solutions, tuple)
        with pytest.raises(FrozenInstanceError):
            catalog.fingerprint = "changed"  # type: ignore[misc]
        templates = reader.templates(campaign_id)
        assert templates is not None and templates.creation_rules_id == "archetype-budget-v1"
        v3["schema_version"] = 2
        for key in ("initial_public_goal", "facts", "conditions", "outcomes", "encounters"):
            del v3[key]
        session.execute(
            text("UPDATE adventures_snapshots SET content = :content"), {"content": json.dumps(v3)}
        )
        legacy = reader.available_encounters(campaign_id)
        assert legacy is not None and legacy.encounters == ()


@pytest.mark.unit
def test_authored_last_shift_has_terminal_diagnostics_without_applying_effects():
    root = Path(__file__).resolve().parents[3] / "adventures/last-shift"
    package = load_package(root)
    data = json.loads(package.content)
    assert data["schema_version"] == 3 and data["edition"] == "1.1"
    assert data["initial_public_goal"] == "Проверить состояние терминала в приёмном шлюзе."
    projection = domain.project_initial_encounters(data, package.fingerprint)
    encounter = projection["encounters"][0]
    assert encounter["id"] == "terminal-diagnostics"
    assert [
        (s["id"], s["check"]["skill_id"], s["check"]["difficulty"]) for s in encounter["solutions"]
    ] == [
        ("repair-terminal", "repair", 5),
        ("restart-terminal", "hacking", 5),
    ]
    assert all(s["check"]["characteristic"] == "intellect" for s in encounter["solutions"])
    assert all(not fact["initial_value"] for fact in data["facts"])

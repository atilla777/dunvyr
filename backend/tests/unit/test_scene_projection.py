"""The player scene must contain only explicitly public starting-location fields."""

import pytest

from dunvyr.adventures.domain import package


@pytest.mark.unit
def test_scene_projection_excludes_hidden_objects_and_future_locations():
    data = {
        "initial_location_id": "start",
        "locations": [
            {
                "id": "start",
                "name": "Airlock",
                "public_description": "A quiet room",
                "illustration": "image",
                "private_fact": "SECRET_FACT",
                "exits": [{"target_location_id": "SECRET_LOCATION"}],
                "objects": [
                    {
                        "id": "box",
                        "name": "Box",
                        "public_description": "A box",
                        "hotspot": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
                        "visibility": "visible",
                        "private_fact": "SECRET_OBJECT_FACT",
                    },
                    {"id": "SECRET_OBJECT", "visibility": "hidden"},
                ],
            },
            {"id": "SECRET_LOCATION"},
        ],
    }
    project = getattr(package, "project_initial_scene", None)
    assert project is not None, "a server-side allowlist projection is required"
    scene = project(data)
    assert scene == {
        "name": "Airlock",
        "description": "A quiet room",
        "illustration": "image",
        "objects": [
            {
                "id": "box",
                "name": "Box",
                "description": "A box",
                "hotspot": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.4},
            }
        ],
    }

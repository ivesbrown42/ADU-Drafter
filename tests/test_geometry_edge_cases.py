from __future__ import annotations

import copy

import pytest

from adu_drafter.contracts import Agent2Output, validate_agent_2_output_against_input


def test_room_overlap_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["rooms"][1]["rect"]["x_ft"] = 5.0
    bad["rooms"][1]["rect"]["y_ft"] = 5.0
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="overlap|outside selected zone bounds|outside zone-local bounds"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_opening_anchor_not_on_wall_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["openings_intent"][0]["anchor_local"] = {"x_ft": 10.0, "y_ft": 14.7}
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="anchor_local"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_geometry_outside_zone_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["walls_intent"][0]["end_local"]["x_ft"] = 25.0
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="outside zone-local bounds"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_invalid_grid_snapping_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["walls_intent"][0]["start_local"]["x_ft"] = 0.3
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="grid_step_ft|grid step"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def valid_agent2_output_payload() -> dict:
    return {
        "agent": "adu-designer-agent-2",
        "version": "1.0",
        "conflict_flag": False,
        "design_summary": {
            "program_id": "program-oversized-capped",
            "zone_id": "zone-1",
            "layout_type": "two-room-split",
        },
        "rooms": [
            {
                "room_id": "living-1",
                "room_type": "living",
                "target_area_sf": 300,
                "rect": {"x_ft": 0, "y_ft": 0, "width_ft": 20, "depth_ft": 15},
                "adjacency": ["bed-1"],
            },
            {
                "room_id": "bed-1",
                "room_type": "bedroom",
                "target_area_sf": 300,
                "rect": {"x_ft": 0, "y_ft": 15, "width_ft": 20, "depth_ft": 15},
                "adjacency": ["living-1"],
            },
        ],
        "walls_intent": [
            {
                "wall_id": "w-ext-bottom",
                "kind": "exterior",
                "start_local": {"x_ft": 0, "y_ft": 0},
                "end_local": {"x_ft": 20, "y_ft": 0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-mid",
                "kind": "interior",
                "start_local": {"x_ft": 0, "y_ft": 15},
                "end_local": {"x_ft": 20, "y_ft": 15},
                "thickness_ft": 0.5,
            },
        ],
        "openings_intent": [
            {
                "opening_id": "door-1",
                "wall_id": "w-int-mid",
                "opening_type": "door",
                "anchor_local": {"x_ft": 10, "y_ft": 15},
                "width_ft": 3.0,
            }
        ],
        "notes": [],
    }


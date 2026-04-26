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


def test_missing_required_bathroom_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["rooms"] = [room for room in bad["rooms"] if room["room_type"] != "bathroom"]
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="MISSING_BATHROOM"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_exterior_loop_open_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["walls_intent"] = [
        wall for wall in bad["walls_intent"] if wall["wall_id"] != "w-ext-left"
    ]
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="EXTERIOR_LOOP_OPEN"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_room_without_door_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["openings_intent"] = [
        opening for opening in bad["openings_intent"] if opening["opening_id"] != "door-bath"
    ]
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="ROOM_DISCONNECTED"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def valid_agent2_output_payload() -> dict:
    return {
        "agent": "adu-designer-agent-2",
        "version": "1.0",
        "conflict_flag": False,
        "design_summary": {
            "program_id": "program-1",
            "zone_id": "zone-1",
            "layout_type": "rectangular-1bed-1bath",
        },
        "rooms": [
            {
                "room_id": "living-1",
                "room_type": "living",
                "label": "LIVING",
                "center_local": {"x_ft": 6.0, "y_ft": 7.5},
                "target_area_sf": 180,
                "rect": {"x_ft": 0, "y_ft": 0, "width_ft": 12, "depth_ft": 15},
                "adjacency": ["kitchen-1", "bed-1"],
            },
            {
                "room_id": "kitchen-1",
                "room_type": "kitchen",
                "label": "KITCHEN",
                "center_local": {"x_ft": 16.0, "y_ft": 7.5},
                "target_area_sf": 120,
                "rect": {"x_ft": 12, "y_ft": 0, "width_ft": 8, "depth_ft": 15},
                "adjacency": ["living-1", "bath-1"],
            },
            {
                "room_id": "bed-1",
                "room_type": "bedroom",
                "label": "BEDROOM",
                "center_local": {"x_ft": 8.0, "y_ft": 22.5},
                "target_area_sf": 240,
                "rect": {"x_ft": 0, "y_ft": 15, "width_ft": 16, "depth_ft": 15},
                "adjacency": ["living-1", "bath-1"],
            },
            {
                "room_id": "bath-1",
                "room_type": "bathroom",
                "label": "BATH",
                "center_local": {"x_ft": 18.0, "y_ft": 22.5},
                "target_area_sf": 60,
                "rect": {"x_ft": 16, "y_ft": 15, "width_ft": 4, "depth_ft": 15},
                "adjacency": ["bed-1", "kitchen-1"],
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
                "wall_id": "w-ext-right",
                "kind": "exterior",
                "start_local": {"x_ft": 20, "y_ft": 0},
                "end_local": {"x_ft": 20, "y_ft": 30},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-ext-top",
                "kind": "exterior",
                "start_local": {"x_ft": 20, "y_ft": 30},
                "end_local": {"x_ft": 0, "y_ft": 30},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-ext-left",
                "kind": "exterior",
                "start_local": {"x_ft": 0, "y_ft": 30},
                "end_local": {"x_ft": 0, "y_ft": 0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-mid",
                "kind": "interior",
                "start_local": {"x_ft": 0, "y_ft": 15},
                "end_local": {"x_ft": 20, "y_ft": 15},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-kitchen",
                "kind": "interior",
                "start_local": {"x_ft": 12, "y_ft": 0},
                "end_local": {"x_ft": 12, "y_ft": 15},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-bath",
                "kind": "interior",
                "start_local": {"x_ft": 16, "y_ft": 15},
                "end_local": {"x_ft": 16, "y_ft": 30},
                "thickness_ft": 0.5,
            },
        ],
        "openings_intent": [
            {
                "opening_id": "door-main",
                "wall_id": "w-ext-bottom",
                "opening_type": "door",
                "anchor_local": {"x_ft": 8, "y_ft": 0},
                "width_ft": 3.0,
            },
            {
                "opening_id": "door-bed",
                "wall_id": "w-int-mid",
                "opening_type": "door",
                "anchor_local": {"x_ft": 8, "y_ft": 15},
                "width_ft": 3.0,
            },
            {
                "opening_id": "door-kitchen",
                "wall_id": "w-int-kitchen",
                "opening_type": "door",
                "anchor_local": {"x_ft": 12, "y_ft": 8},
                "width_ft": 3.0,
            },
            {
                "opening_id": "door-bath",
                "wall_id": "w-int-bath",
                "opening_type": "door",
                "anchor_local": {"x_ft": 16, "y_ft": 22},
                "width_ft": 3.0,
            }
        ],
        "notes": [],
    }


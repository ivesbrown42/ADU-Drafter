from __future__ import annotations

import copy

import pytest

from adu_drafter.contracts import (
    Agent2Output,
    RoomMinimumGuideline,
    validate_agent_2_output_against_input,
)


def test_room_overlap_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["rooms"][1]["rect"]["x_ft"] = 5.0
    bad["rooms"][1]["rect"]["y_ft"] = 5.0
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="overlap|outside selected zone bounds|outside zone-local bounds"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_opening_anchor_not_on_wall_is_soft_only(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["openings_intent"][0]["anchor_local"] = {"x_ft": 9.5, "y_ft": 10.0}
    model = Agent2Output.model_validate(bad)
    # Opening-on-host-wall fidelity is telemetry-only in the operational matrix.
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


def test_open_plan_required_for_1br_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["rooms"] = [
        {
            "room_id": "living-1",
            "room_type": "living",
            "label": "LIVING",
            "center_local": {"x_ft": 6.0, "y_ft": 5.0},
            "target_area_sf": 120,
            "rect": {"x_ft": 0, "y_ft": 0, "width_ft": 12, "depth_ft": 10},
            "adjacency": ["kitchen-1", "bath-1"],
        },
        {
            "room_id": "kitchen-1",
            "room_type": "kitchen",
            "label": "KITCHEN",
            "center_local": {"x_ft": 16.0, "y_ft": 5.0},
            "target_area_sf": 80,
            "rect": {"x_ft": 12, "y_ft": 0, "width_ft": 8, "depth_ft": 10},
            "adjacency": ["living-1", "bath-1"],
        },
    ] + [room for room in bad["rooms"] if room["room_type"] != "open_living_kitchen"]
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="OPEN_PLAN_REQUIRED"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_bathroom_proportion_violation_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bath = next(room for room in bad["rooms"] if room["room_type"] == "bathroom")
    bath["rect"]["width_ft"] = 4.0
    bath["center_local"] = {"x_ft": 17.0, "y_ft": 14.5}
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="PROPORTION_VIOLATION"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_zone_order_violation_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bath = next(room for room in bad["rooms"] if room["room_type"] == "bathroom")
    bath["rect"]["x_ft"] = 15.0
    bath["rect"]["y_ft"] = 21.0
    bath["rect"]["width_ft"] = 5.0
    bath["rect"]["depth_ft"] = 9.0
    bath["center_local"] = {"x_ft": 17.5, "y_ft": 25.5}
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="ZONE_ORDER_VIOLATION"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_exterior_loop_open_is_soft_only(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["walls_intent"] = [
        wall for wall in bad["walls_intent"] if wall["wall_id"] != "w-ext-left"
    ]
    model = Agent2Output.model_validate(bad)
    # Exterior shell-loop completeness is telemetry-only in Phase 1.
    validate_agent_2_output_against_input(valid_agent2_input, model)


def test_room_without_door_rejected(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bad["openings_intent"] = [
        opening for opening in bad["openings_intent"] if opening["opening_id"] != "door-bath"
    ]
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="ROOM_DISCONNECTED"):
        validate_agent_2_output_against_input(valid_agent2_input, model)


def test_layout_heuristics_override_room_minimums(valid_agent2_input):
    bad = copy.deepcopy(valid_agent2_output_payload())
    bath = next(room for room in bad["rooms"] if room["room_type"] == "bathroom")
    bath["rect"]["width_ft"] = 4.5
    bath["center_local"] = {"x_ft": 17.25, "y_ft": 14.5}
    model = Agent2Output.model_validate(bad)
    with pytest.raises(ValueError, match="PROPORTION_VIOLATION"):
        validate_agent_2_output_against_input(valid_agent2_input, model)

    # Agent2Input can override minimums via deterministic layout heuristics.
    valid_agent2_input.design_rules.layout_heuristics.room_minimums = [
        RoomMinimumGuideline(
            room_type="bathroom",
            label="Bathroom",
            min_width_ft=4.0,
            min_depth_ft=7.5,
            min_area_sf=36.0,
        )
    ]
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
                "room_id": "open-lk-1",
                "room_type": "open_living_kitchen",
                "label": "OPEN LIVING/KITCHEN",
                "center_local": {"x_ft": 10.0, "y_ft": 5.0},
                "target_area_sf": 200,
                "rect": {"x_ft": 0, "y_ft": 0, "width_ft": 20, "depth_ft": 10},
                "adjacency": ["bath-1", "bed-1"],
            },
            {
                "room_id": "bed-1",
                "room_type": "bedroom",
                "label": "BEDROOM",
                "center_local": {"x_ft": 7.5, "y_ft": 24.5},
                "target_area_sf": 165,
                "rect": {"x_ft": 0, "y_ft": 19, "width_ft": 15, "depth_ft": 11},
                "adjacency": ["open-lk-1", "bath-1"],
            },
            {
                "room_id": "bath-1",
                "room_type": "bathroom",
                "label": "BATH",
                "center_local": {"x_ft": 17.5, "y_ft": 14.5},
                "target_area_sf": 45,
                "rect": {"x_ft": 15, "y_ft": 10, "width_ft": 5, "depth_ft": 9},
                "adjacency": ["open-lk-1", "bed-1"],
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
                "wall_id": "w-int-open-top",
                "kind": "interior",
                "start_local": {"x_ft": 0, "y_ft": 10},
                "end_local": {"x_ft": 20, "y_ft": 10},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-bed-bottom",
                "kind": "interior",
                "start_local": {"x_ft": 0, "y_ft": 19},
                "end_local": {"x_ft": 15, "y_ft": 19},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-bath-left",
                "kind": "interior",
                "start_local": {"x_ft": 15, "y_ft": 10},
                "end_local": {"x_ft": 15, "y_ft": 19},
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
                "wall_id": "w-int-bed-bottom",
                "opening_type": "door",
                "anchor_local": {"x_ft": 7.5, "y_ft": 19},
                "width_ft": 3.0,
            },
            {
                "opening_id": "door-bath",
                "wall_id": "w-int-bath-left",
                "opening_type": "door",
                "anchor_local": {"x_ft": 15, "y_ft": 14.5},
                "width_ft": 3.0,
            }
        ],
        "notes": [],
    }


from __future__ import annotations

import json
from argparse import Namespace
from pathlib import Path

from adu_drafter.orchestrate import run_orchestration


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _valid_agent1_input() -> dict:
    return {
        "site_metadata": {
            "lot_id": "lot-retry",
            "rectangular_lot": True,
            "lot_width_ft": 50.0,
            "lot_depth_ft": 120.0,
            "street_frontage": "south",
            "origin_corner": "SW",
        },
        "existing_structures": [
            {
                "id": "s1",
                "label": "Primary Dwelling",
                "is_primary_dwelling": True,
                "offset_from_origin_x_ft": 10.0,
                "offset_from_origin_y_ft": 20.0,
                "width_ft": 30.0,
                "depth_ft": 35.0,
            }
        ],
        "primary_dwelling_walls": [{"wall_label": "PD-REAR", "wall_role": "rear"}],
        "candidate_zones": [
            {
                "zone_id": "zone-1",
                "strategy": "rear-left",
                "zone_polygon_sw_origin": [[4.0, 80.0], [24.0, 80.0], [24.0, 110.0], [4.0, 110.0]],
                "check_results": {
                    "check_1_rear_setback": True,
                    "check_2_side_setback": True,
                    "check_3_front_constraint": True,
                    "check_4_primary_separation": True,
                    "check_5_other_structure_separation": True,
                },
                "metrics": {"rear_setback_ft": 4.0, "side_setback_ft": 4.0, "clearance_to_primary_ft": 12.0},
                "failed_reason_codes": [],
            }
        ],
        "program_catalog": [
            {
                "program_id": "program-1",
                "bedrooms": 1,
                "bathrooms": 1,
                "target_area_sf": 600.0,
                "footprint_width_ft": 20.0,
                "footprint_depth_ft": 30.0,
            }
        ],
        "client_request": {
            "target_size_sf": 600.0,
            "bedrooms_preference": 1,
            "bathrooms_preference": 1,
            "transit_proximity": False,
        },
    }


def _valid_agent1_output() -> dict:
    return {
        "agent": "site-decision-agent-1",
        "version": "1.0",
        "conflict_flag": False,
        "conflict_reasons": [],
        "decision_summary": {
            "selected_strategy": "rear-left",
            "selected_zone_id": "zone-1",
            "selected_program_id": "program-1",
            "primary_dwelling_rear_wall_label": "PD-REAR",
        },
        "compliance_trace": [
            {
                "zone_id": "zone-1",
                "strategy": "rear-left",
                "check_results": {
                    "check_1_rear_setback": True,
                    "check_2_side_setback": True,
                    "check_3_front_constraint": True,
                    "check_4_primary_separation": True,
                    "check_5_other_structure_separation": True,
                },
                "status": "accepted",
                "reason_codes": [],
            }
        ],
        "for_agent_2": {
            "zone_id": "zone-1",
            "program_id": "program-1",
            "strategy": "rear-left",
            "constraints_profile_id": "constraints-v1",
        },
        "structure_separations": [
            {
                "label": "Primary Dwelling",
                "clearance_ft": 12.0,
                "minimum_required_ft": 6.0,
                "compliant": True,
            }
        ],
        "notes": [],
    }


def _valid_agent2_output() -> dict:
    return {
        "agent": "adu-designer-agent-2",
        "version": "1.0",
        "conflict_flag": False,
        "design_summary": {"program_id": "program-1", "zone_id": "zone-1", "layout_type": "split"},
        "rooms": [
            {
                "room_id": "r1",
                "room_type": "living",
                "target_area_sf": 300.0,
                "rect": {"x_ft": 0.0, "y_ft": 0.0, "width_ft": 20.0, "depth_ft": 15.0},
                "adjacency": [],
            },
            {
                "room_id": "r2",
                "room_type": "bedroom",
                "target_area_sf": 300.0,
                "rect": {"x_ft": 0.0, "y_ft": 15.0, "width_ft": 20.0, "depth_ft": 15.0},
                "adjacency": [],
            },
        ],
        "walls_intent": [
            {
                "wall_id": "w1",
                "kind": "interior",
                "start_local": {"x_ft": 0.0, "y_ft": 15.0},
                "end_local": {"x_ft": 20.0, "y_ft": 15.0},
                "thickness_ft": 0.5,
            }
        ],
        "openings_intent": [
            {
                "opening_id": "o1",
                "wall_id": "w1",
                "opening_type": "door",
                "anchor_local": {"x_ft": 10.0, "y_ft": 15.0},
                "width_ft": 3.0,
            }
        ],
        "notes": [],
    }


def test_orchestrator_retry_exhausts_on_invalid_agent2(tmp_path: Path):
    a1_in = tmp_path / "agent_1_input.json"
    a1_out = tmp_path / "agent_1_output.json"
    a2_out = tmp_path / "agent_2_output.json"
    resolver_out = tmp_path / "geometry_resolver_input.json"
    conflict_out = tmp_path / "conflict.json"

    _write(a1_in, _valid_agent1_input())
    _write(a1_out, _valid_agent1_output())
    invalid = _valid_agent2_output()
    invalid["openings_intent"][0]["anchor_local"]["y_ft"] = 14.75  # not on host wall
    _write(a2_out, invalid)

    args = Namespace(
        agent_1_input=a1_in,
        agent_1_output=a1_out,
        agent_2_output=a2_out,
        resolver_output=resolver_out,
        conflict_output=conflict_out,
        retry_poll_seconds=0.0,
        grid_step_ft=0.5,
        wall_thickness_options_ft=[0.35, 0.5],
        max_retry_iteration=3,
        schema_retries=2,
        input_coordinates_normalized_to_sw=True,
    )

    try:
        run_orchestration(args)
        assert False, "Expected run_orchestration to fail after retry exhaustion"
    except ValueError as exc:
        assert "failed after 2 attempts" in str(exc)


def test_orchestrator_succeeds_with_valid_agent2(tmp_path: Path):
    a1_in = tmp_path / "agent_1_input.json"
    a1_out = tmp_path / "agent_1_output.json"
    a2_out = tmp_path / "agent_2_output.json"
    resolver_out = tmp_path / "geometry_resolver_input.json"
    conflict_out = tmp_path / "conflict.json"

    _write(a1_in, _valid_agent1_input())
    _write(a1_out, _valid_agent1_output())
    _write(a2_out, _valid_agent2_output())

    args = Namespace(
        agent_1_input=a1_in,
        agent_1_output=a1_out,
        agent_2_output=a2_out,
        resolver_output=resolver_out,
        conflict_output=conflict_out,
        retry_poll_seconds=0.0,
        grid_step_ft=0.5,
        wall_thickness_options_ft=[0.35, 0.5],
        max_retry_iteration=3,
        schema_retries=3,
        input_coordinates_normalized_to_sw=True,
    )
    code = run_orchestration(args)
    assert code == 0
    assert resolver_out.exists()


def test_orchestrator_retry_succeeds_on_second_attempt(tmp_path: Path, monkeypatch):
    a1_in = tmp_path / "agent_1_input.json"
    a1_out = tmp_path / "agent_1_output.json"
    a2_out = tmp_path / "agent_2_output.json"
    resolver_out = tmp_path / "geometry_resolver_input.json"
    conflict_out = tmp_path / "conflict.json"

    _write(a1_in, _valid_agent1_input())
    _write(a1_out, _valid_agent1_output())

    invalid = _valid_agent2_output()
    invalid["openings_intent"][0]["anchor_local"]["y_ft"] = 14.75
    _write(a2_out, invalid)

    valid = _valid_agent2_output()
    calls = {"count": 0}

    import adu_drafter.orchestrate as orch

    original_loader = orch.load_agent_2_output

    def flaky_loader(path):
        calls["count"] += 1
        if calls["count"] == 2:
            _write(a2_out, valid)
        return original_loader(path)

    monkeypatch.setattr(orch, "load_agent_2_output", flaky_loader)

    args = Namespace(
        agent_1_input=a1_in,
        agent_1_output=a1_out,
        agent_2_output=a2_out,
        resolver_output=resolver_out,
        conflict_output=conflict_out,
        retry_poll_seconds=0.0,
        grid_step_ft=0.5,
        wall_thickness_options_ft=[0.35, 0.5],
        max_retry_iteration=3,
        schema_retries=3,
        input_coordinates_normalized_to_sw=True,
    )

    code = run_orchestration(args)
    assert code == 0
    assert calls["count"] >= 1
    assert resolver_out.exists()

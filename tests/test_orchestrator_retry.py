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
    def _room(
        room_id: str,
        room_type: str,
        target_area_sf: float,
        x_ft: float,
        y_ft: float,
        width_ft: float,
        depth_ft: float,
        adjacency: list[str],
        label: str,
    ) -> dict:
        return {
            "room_id": room_id,
            "room_type": room_type,
            "target_area_sf": target_area_sf,
            "rect": {
                "x_ft": x_ft,
                "y_ft": y_ft,
                "width_ft": width_ft,
                "depth_ft": depth_ft,
            },
            "adjacency": adjacency,
            "label": label,
            "center_local": {
                "x_ft": x_ft + (width_ft / 2.0),
                "y_ft": y_ft + (depth_ft / 2.0),
            },
        }

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
            _room(
                "open-lk-1",
                "open_living_kitchen",
                200.0,
                0.0,
                0.0,
                20.0,
                10.0,
                ["bed-1", "bath-1"],
                "OPEN LIVING/KITCHEN",
            ),
            _room("bed-1", "bedroom", 165.0, 0.0, 19.0, 15.0, 11.0, ["open-lk-1", "bath-1"], "BEDROOM"),
            _room("bath-1", "bathroom", 45.0, 15.0, 10.0, 5.0, 9.0, ["open-lk-1", "bed-1"], "BATH"),
        ],
        "walls_intent": [
            {
                "wall_id": "w-ext-bottom",
                "kind": "exterior",
                "start_local": {"x_ft": 0.0, "y_ft": 0.0},
                "end_local": {"x_ft": 20.0, "y_ft": 0.0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-ext-right",
                "kind": "exterior",
                "start_local": {"x_ft": 20.0, "y_ft": 0.0},
                "end_local": {"x_ft": 20.0, "y_ft": 30.0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-ext-top",
                "kind": "exterior",
                "start_local": {"x_ft": 20.0, "y_ft": 30.0},
                "end_local": {"x_ft": 0.0, "y_ft": 30.0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-ext-left",
                "kind": "exterior",
                "start_local": {"x_ft": 0.0, "y_ft": 30.0},
                "end_local": {"x_ft": 0.0, "y_ft": 0.0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-mid",
                "kind": "interior",
                "start_local": {"x_ft": 0.0, "y_ft": 10.0},
                "end_local": {"x_ft": 20.0, "y_ft": 10.0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-bed-bottom",
                "kind": "interior",
                "start_local": {"x_ft": 0.0, "y_ft": 19.0},
                "end_local": {"x_ft": 15.0, "y_ft": 19.0},
                "thickness_ft": 0.5,
            },
            {
                "wall_id": "w-int-bath-left",
                "kind": "interior",
                "start_local": {"x_ft": 15.0, "y_ft": 10.0},
                "end_local": {"x_ft": 15.0, "y_ft": 19.0},
                "thickness_ft": 0.5,
            }
        ],
        "openings_intent": [
            {
                "opening_id": "door-main",
                "wall_id": "w-ext-bottom",
                "opening_type": "door",
                "anchor_local": {"x_ft": 8.0, "y_ft": 0.0},
                "width_ft": 3.0,
            },
            {
                "opening_id": "door-bed",
                "wall_id": "w-int-bed-bottom",
                "opening_type": "door",
                "anchor_local": {"x_ft": 7.5, "y_ft": 19.0},
                "width_ft": 3.0,
            },
            {
                "opening_id": "door-bath",
                "wall_id": "w-int-bath-left",
                "opening_type": "door",
                "anchor_local": {"x_ft": 15.0, "y_ft": 14.5},
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
    invalid["openings_intent"][1]["anchor_local"]["y_ft"] = 31.0  # outside footprint bounds
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
    invalid["openings_intent"][1]["anchor_local"]["y_ft"] = 31.0
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


def test_orchestrator_best_of_n_selects_highest_scoring_valid_candidate(
    tmp_path: Path, monkeypatch
):
    a1_in = tmp_path / "agent_1_input.json"
    a1_out = tmp_path / "agent_1_output.json"
    a2_candidate_1 = tmp_path / "agent_2_output_candidate_1.json"
    a2_candidate_2 = tmp_path / "agent_2_output_candidate_2.json"
    resolver_out = tmp_path / "geometry_resolver_input.json"
    conflict_out = tmp_path / "conflict.json"

    _write(a1_in, _valid_agent1_input())
    _write(a1_out, _valid_agent1_output())

    candidate_1 = _valid_agent2_output()
    candidate_1["design_summary"]["layout_type"] = "candidate-one"
    candidate_2 = _valid_agent2_output()
    candidate_2["design_summary"]["layout_type"] = "candidate-two"
    _write(a2_candidate_1, candidate_1)
    _write(a2_candidate_2, candidate_2)

    import adu_drafter.orchestrate as orch

    def fake_score(_agent_2_input, candidate):
        layout_type = candidate.design_summary.layout_type
        if layout_type == "candidate-one":
            return {"score": 70}
        return {"score": 95}

    monkeypatch.setattr(orch, "score_agent_2_layout", fake_score)

    args = Namespace(
        agent_1_input=a1_in,
        agent_1_output=a1_out,
        agent_2_output=None,
        agent_2_candidate_outputs=[a2_candidate_1, a2_candidate_2],
        best_of_n=2,
        duplicate_candidate_penalty=15,
        reject_duplicate_candidates=False,
        resolver_output=resolver_out,
        conflict_output=conflict_out,
        retry_poll_seconds=0.0,
        grid_step_ft=0.5,
        wall_thickness_options_ft=[0.35, 0.5],
        max_retry_iteration=3,
        schema_retries=2,
        input_coordinates_normalized_to_sw=True,
    )

    code = run_orchestration(args)
    assert code == 0
    resolver_payload = json.loads(resolver_out.read_text(encoding="utf-8"))
    assert resolver_payload["agent_2_output"]["design_summary"]["layout_type"] == "candidate-two"


def test_orchestrator_best_of_n_skips_invalid_candidates_and_selects_valid(
    tmp_path: Path,
):
    a1_in = tmp_path / "agent_1_input.json"
    a1_out = tmp_path / "agent_1_output.json"
    a2_candidate_bad = tmp_path / "agent_2_output_candidate_bad.json"
    a2_candidate_good = tmp_path / "agent_2_output_candidate_good.json"
    resolver_out = tmp_path / "geometry_resolver_input.json"
    conflict_out = tmp_path / "conflict.json"

    _write(a1_in, _valid_agent1_input())
    _write(a1_out, _valid_agent1_output())

    invalid = _valid_agent2_output()
    invalid["openings_intent"][1]["anchor_local"]["y_ft"] = 31.0
    valid = _valid_agent2_output()
    valid["design_summary"]["layout_type"] = "valid-candidate"
    _write(a2_candidate_bad, invalid)
    _write(a2_candidate_good, valid)

    args = Namespace(
        agent_1_input=a1_in,
        agent_1_output=a1_out,
        agent_2_output=None,
        agent_2_candidate_outputs=[a2_candidate_bad, a2_candidate_good],
        best_of_n=2,
        duplicate_candidate_penalty=15,
        reject_duplicate_candidates=False,
        resolver_output=resolver_out,
        conflict_output=conflict_out,
        retry_poll_seconds=0.0,
        grid_step_ft=0.5,
        wall_thickness_options_ft=[0.35, 0.5],
        max_retry_iteration=3,
        schema_retries=1,
        input_coordinates_normalized_to_sw=True,
    )

    code = run_orchestration(args)
    assert code == 0
    resolver_payload = json.loads(resolver_out.read_text(encoding="utf-8"))
    assert resolver_payload["agent_2_output"]["design_summary"]["layout_type"] == "valid-candidate"


def test_orchestrator_best_of_n_penalizes_duplicate_geometry(
    tmp_path: Path, monkeypatch
):
    a1_in = tmp_path / "agent_1_input.json"
    a1_out = tmp_path / "agent_1_output.json"
    a2_candidate_1 = tmp_path / "agent_2_output_candidate_1.json"
    a2_candidate_2 = tmp_path / "agent_2_output_candidate_2.json"
    resolver_out = tmp_path / "geometry_resolver_input.json"
    conflict_out = tmp_path / "conflict.json"

    _write(a1_in, _valid_agent1_input())
    _write(a1_out, _valid_agent1_output())

    candidate_1 = _valid_agent2_output()
    candidate_1["design_summary"]["layout_type"] = "duplicate-a"
    candidate_2 = _valid_agent2_output()
    candidate_2["design_summary"]["layout_type"] = "duplicate-b"
    _write(a2_candidate_1, candidate_1)
    _write(a2_candidate_2, candidate_2)

    import adu_drafter.orchestrate as orch

    def fake_score(_agent_2_input, _candidate):
        # Same soft score; duplicate penalty should make candidate 1 win.
        return {"score": 95}

    monkeypatch.setattr(orch, "score_agent_2_layout", fake_score)

    args = Namespace(
        agent_1_input=a1_in,
        agent_1_output=a1_out,
        agent_2_output=None,
        agent_2_candidate_outputs=[a2_candidate_1, a2_candidate_2],
        best_of_n=2,
        duplicate_candidate_penalty=15,
        reject_duplicate_candidates=False,
        resolver_output=resolver_out,
        conflict_output=conflict_out,
        retry_poll_seconds=0.0,
        grid_step_ft=0.5,
        wall_thickness_options_ft=[0.35, 0.5],
        max_retry_iteration=3,
        schema_retries=2,
        input_coordinates_normalized_to_sw=True,
    )

    code = run_orchestration(args)
    assert code == 0
    resolver_payload = json.loads(resolver_out.read_text(encoding="utf-8"))
    assert resolver_payload["agent_2_output"]["design_summary"]["layout_type"] == "duplicate-a"


def test_orchestrator_best_of_n_rejects_duplicate_geometry_when_enabled(
    tmp_path: Path, monkeypatch
):
    a1_in = tmp_path / "agent_1_input.json"
    a1_out = tmp_path / "agent_1_output.json"
    a2_candidate_1 = tmp_path / "agent_2_output_candidate_1.json"
    a2_candidate_2 = tmp_path / "agent_2_output_candidate_2.json"
    a2_candidate_3 = tmp_path / "agent_2_output_candidate_3.json"
    resolver_out = tmp_path / "geometry_resolver_input.json"
    conflict_out = tmp_path / "conflict.json"

    _write(a1_in, _valid_agent1_input())
    _write(a1_out, _valid_agent1_output())

    duplicate_1 = _valid_agent2_output()
    duplicate_1["design_summary"]["layout_type"] = "duplicate-a"
    duplicate_2 = _valid_agent2_output()
    duplicate_2["design_summary"]["layout_type"] = "duplicate-b"
    unique_3 = _valid_agent2_output()
    unique_3["design_summary"]["layout_type"] = "unique-c"
    # Make candidate 3 unique with a minor geometry shift.
    unique_3["openings_intent"][0]["anchor_local"]["x_ft"] = 9.0

    _write(a2_candidate_1, duplicate_1)
    _write(a2_candidate_2, duplicate_2)
    _write(a2_candidate_3, unique_3)

    import adu_drafter.orchestrate as orch

    def fake_score(_agent_2_input, candidate):
        layout_type = candidate.design_summary.layout_type
        if layout_type == "duplicate-a":
            return {"score": 90}
        if layout_type == "duplicate-b":
            return {"score": 99}
        return {"score": 95}

    monkeypatch.setattr(orch, "score_agent_2_layout", fake_score)

    args = Namespace(
        agent_1_input=a1_in,
        agent_1_output=a1_out,
        agent_2_output=None,
        agent_2_candidate_outputs=[a2_candidate_1, a2_candidate_2, a2_candidate_3],
        best_of_n=3,
        duplicate_candidate_penalty=15,
        reject_duplicate_candidates=True,
        resolver_output=resolver_out,
        conflict_output=conflict_out,
        retry_poll_seconds=0.0,
        grid_step_ft=0.5,
        wall_thickness_options_ft=[0.35, 0.5],
        max_retry_iteration=3,
        schema_retries=2,
        input_coordinates_normalized_to_sw=True,
    )

    code = run_orchestration(args)
    assert code == 0
    resolver_payload = json.loads(resolver_out.read_text(encoding="utf-8"))
    # Duplicate-b has the highest score but is duplicate and should be skipped.
    assert resolver_payload["agent_2_output"]["design_summary"]["layout_type"] == "unique-c"

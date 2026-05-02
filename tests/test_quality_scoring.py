from __future__ import annotations

import json
from pathlib import Path

from adu_drafter.contracts import Agent1Input, Agent1Output, Agent2Output, build_agent_2_input
from adu_drafter.quality_scoring import score_agent2_layout


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def test_quality_score_happy_case_emits_soft_telemetry() -> None:
    agent1_input_payload = _load_json("tests/fixtures/golden/agent_1_input.json")
    agent1_output_payload = _load_json("tests/fixtures/golden/agent_1_output.json")
    agent2_output_payload = _load_json("data/eval_cases/case_happy/agent_2_output.json")

    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    agent2_output = Agent2Output.model_validate(agent2_output_payload)

    score = score_agent2_layout(agent2_input, agent2_output)

    assert 0 <= score["score"] <= 100
    assert score["deductions"]
    assert score["metadata"]["sections_6_7_dropped"] is True
    assert score["status"] in {"PASS", "SOFT_FAIL", "HARD_FAIL"}


def test_quality_score_no_windows_or_swing_rules_present() -> None:
    agent1_input_payload = _load_json("tests/fixtures/golden/agent_1_input.json")
    agent1_output_payload = _load_json("tests/fixtures/golden/agent_1_output.json")
    agent2_output_payload = _load_json("data/eval_cases/case_happy/agent_2_output.json")

    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    agent2_output = Agent2Output.model_validate(agent2_output_payload)

    score = score_agent2_layout(agent2_input, agent2_output)
    codes = {item["code"] for item in score["deductions"]}
    assert all("WINDOW" not in code for code in codes)
    assert all("DOOR_SWING" not in code for code in codes)


def test_quality_score_convexity_rectangularity_no_penalty_for_compact_layout() -> None:
    agent1_input_payload = _load_json("tests/fixtures/golden/agent_1_input.json")
    agent1_output_payload = _load_json("tests/fixtures/golden/agent_1_output.json")
    agent2_output_payload = _load_json("data/eval_cases/case_happy/agent_2_output_candidate_better.json")

    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    agent2_output = Agent2Output.model_validate(agent2_output_payload)

    # Repack rooms into a simple contiguous rectangle to avoid shape penalties.
    for room in agent2_output.rooms:
        if room.room_id == "open-lk-1":
            room.rect.x_ft = 0
            room.rect.y_ft = 0
            room.rect.width_ft = 15
            room.rect.depth_ft = 10
        elif room.room_id == "bath-1":
            room.rect.x_ft = 0
            room.rect.y_ft = 10
            room.rect.width_ft = 5
            room.rect.depth_ft = 9
        elif room.room_id == "storage-1":
            room.rect.x_ft = 5
            room.rect.y_ft = 10
            room.rect.width_ft = 10
            room.rect.depth_ft = 9
        elif room.room_id == "bed-1":
            room.rect.x_ft = 0
            room.rect.y_ft = 19
            room.rect.width_ft = 15
            room.rect.depth_ft = 11

    score = score_agent2_layout(agent2_input, agent2_output)
    codes = {item["code"] for item in score["deductions"]}

    assert "LAYOUT_CONVEXITY_GAP" not in codes
    assert "LAYOUT_RECTANGULARITY_LOW" not in codes
    assert "SINGLETON_ROOM_ZONE_NON_RECTANGULAR" not in codes
    assert score["metadata"]["layout_axis_convex"] is True
    assert score["metadata"]["layout_rectangularity_ratio"] == 1.0


def test_quality_score_convexity_rectangularity_penalizes_fragmented_layout() -> None:
    agent1_input_payload = _load_json("tests/fixtures/golden/agent_1_input.json")
    agent1_output_payload = _load_json("tests/fixtures/golden/agent_1_output.json")
    agent2_output_payload = _load_json("data/eval_cases/case_happy/agent_2_output_candidate_better.json")

    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    agent2_output = Agent2Output.model_validate(agent2_output_payload)

    # Move storage to create an upper-left notch and split occupancy in x/y slices.
    for room in agent2_output.rooms:
        if room.room_id == "storage-1":
            room.rect.x_ft = 0
            room.rect.y_ft = 20
            break

    score = score_agent2_layout(agent2_input, agent2_output)
    deductions_by_code = {item["code"]: item for item in score["deductions"]}

    assert "LAYOUT_CONVEXITY_GAP" in deductions_by_code
    assert deductions_by_code["LAYOUT_CONVEXITY_GAP"]["penalty"] == 10
    assert "LAYOUT_RECTANGULARITY_LOW" in deductions_by_code
    assert deductions_by_code["LAYOUT_RECTANGULARITY_LOW"]["penalty"] == 8
    assert score["metadata"]["layout_axis_convex"] is False
    assert score["metadata"]["layout_rectangularity_ratio"] < 0.8


def test_quality_score_singleton_room_zone_penalizes_wraparound_split() -> None:
    agent1_input_payload = _load_json("tests/fixtures/golden/agent_1_input.json")
    agent1_output_payload = _load_json("tests/fixtures/golden/agent_1_output.json")
    agent2_output_payload = _load_json("data/eval_cases/case_happy/agent_2_output_candidate_better.json")

    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    agent2_output = Agent2Output.model_validate(agent2_output_payload)

    # Simulate the anomaly: bedroom emitted as two wrapped/split pieces.
    for room in agent2_output.rooms:
        if room.room_id == "bed-1":
            room.rect.x_ft = 0
            room.rect.y_ft = 19
            room.rect.width_ft = 5
            room.rect.depth_ft = 11
            break
    duplicate_bedroom_piece = agent2_output.rooms[1].model_copy(deep=True)
    duplicate_bedroom_piece.room_id = "bed-1-wing"
    duplicate_bedroom_piece.rect.x_ft = 10
    duplicate_bedroom_piece.rect.y_ft = 19
    duplicate_bedroom_piece.rect.width_ft = 5
    duplicate_bedroom_piece.rect.depth_ft = 11
    agent2_output.rooms.append(duplicate_bedroom_piece)

    score = score_agent2_layout(agent2_input, agent2_output)
    deductions_by_code = {item["code"]: item for item in score["deductions"]}
    assert "ROOM_ZONE_RECTANGULARITY_LOW" in deductions_by_code
    assert deductions_by_code["ROOM_ZONE_RECTANGULARITY_LOW"]["penalty"] == 15


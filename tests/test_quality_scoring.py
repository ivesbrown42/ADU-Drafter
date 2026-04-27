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


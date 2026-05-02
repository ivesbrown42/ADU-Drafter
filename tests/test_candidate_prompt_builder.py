from __future__ import annotations

import json
from pathlib import Path

from adu_drafter.contracts import Agent1Input, Agent1Output, build_agent_2_input
from scripts.build_agent2_candidate_prompts import (
    build_anchor_variations,
    build_candidate_prompt_payloads,
    write_candidate_prompt_payloads,
)


def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _build_agent2_input_payload() -> dict:
    agent1_input_payload = _load_json("tests/fixtures/golden/agent_1_input.json")
    agent1_output_payload = _load_json("tests/fixtures/golden/agent_1_output.json")
    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    return agent2_input.model_dump(mode="json")


def test_build_anchor_variations_has_five_distinct_directives() -> None:
    directives = build_anchor_variations(_build_agent2_input_payload())
    assert len(directives) == 5
    assert len({directive.directive_id for directive in directives}) == 5
    assert directives[0].directive_id == "anchor_north_bedroom"
    assert directives[4].directive_id == "anchor_southern_half_living"


def test_build_candidate_prompt_payloads_embeds_variation_directives() -> None:
    agent2_input = _build_agent2_input_payload()
    payloads = build_candidate_prompt_payloads(agent2_input, candidate_count=5)
    assert len(payloads) == 5

    first = payloads[0]
    assert first["candidate_id"] == "candidate_1"
    assert first["generation_config"]["temperature"] == 0.7
    assert first["generation_config"]["top_p"] == 0.9
    assert "NORTH exterior wall" in first["semantic_jitter"]["directive_text"]
    assert first["agent_2_input"] == agent2_input

    fifth = payloads[4]
    assert fifth["candidate_id"] == "candidate_5"
    assert "SOUTHERN half" in fifth["semantic_jitter"]["directive_text"]


def test_write_candidate_prompt_payloads_outputs_expected_files(tmp_path: Path) -> None:
    agent2_input = _build_agent2_input_payload()
    payloads = build_candidate_prompt_payloads(agent2_input, candidate_count=5)
    write_candidate_prompt_payloads(payloads, tmp_path)

    files = sorted(tmp_path.glob("agent2_candidate_prompt_[0-9]_*.json"))
    assert len(files) == 5
    loaded = json.loads(files[2].read_text(encoding="utf-8"))
    assert loaded["candidate_id"] == "candidate_3"
    assert loaded["semantic_jitter"]["directive_id"] == "anchor_east_bedroom"

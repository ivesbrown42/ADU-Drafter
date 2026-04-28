from __future__ import annotations

import copy

import pytest

from adu_drafter.contracts import (
    Agent1Input,
    Agent1Output,
    ProgramCatalogEntry,
    build_agent_2_input,
)


@pytest.mark.parametrize(
    ("fixture_name", "expected_size"),
    [
        ("oversized", 1200.0),
        ("garage_block", 600.0),
        ("transit_bonus", 750.0),
    ],
    ids=["oversized", "garage_block", "transit_bonus"],
)
def test_agent1_input_fixture_loads(
    load_fixture_json, fixture_name: str, expected_size: float
) -> None:
    payload = load_fixture_json(fixture_name, "agent_1_input.json")
    model = Agent1Input.model_validate(payload)
    assert model.client_request.target_size_sf == expected_size


def test_agent1_requires_rectangular_lot(load_fixture_json) -> None:
    payload = load_fixture_json("oversized", "agent_1_input.json")
    payload["site_metadata"]["rectangular_lot"] = False
    with pytest.raises(ValueError):
        Agent1Input.model_validate(payload)


def test_oversized_program_entry_detected(load_fixture_json) -> None:
    payload = load_fixture_json("oversized", "agent_1_input.json")
    entry = ProgramCatalogEntry.model_validate(payload["program_catalog"][0])
    assert entry.target_area_sf == 800.0


def test_build_agent2_input_includes_1br_layout_rules(load_fixture_json) -> None:
    agent1_input_payload = load_fixture_json("golden", "agent_1_input.json")
    agent1_output_payload = load_fixture_json("golden", "agent_1_output.json")
    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)

    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    rules = agent2_input.layout_rules

    assert rules.open_plan_required is True
    assert rules.plumbing_core_required is True
    assert rules.long_axis == "y"
    assert rules.required_room_counts["open_living_kitchen"] == 1
    assert rules.minimum_room_dimensions["bathroom"].min_width_ft == 5.0


def test_build_agent2_input_includes_2br_layout_rules(load_fixture_json) -> None:
    agent1_input_payload = load_fixture_json("oversized", "agent_1_input.json")
    agent1_output_payload = load_fixture_json("golden", "agent_1_output.json")
    agent1_output_payload = copy.deepcopy(agent1_output_payload)
    agent1_output_payload["decision_summary"]["selected_program_id"] = "program-oversized-capped"
    agent1_output_payload["for_agent_2"]["program_id"] = "program-oversized-capped"

    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    agent2_input = build_agent_2_input(agent1_input, agent1_output)
    rules = agent2_input.layout_rules

    assert rules.open_plan_required is False
    assert rules.plumbing_core_required is True
    assert rules.long_axis == "y"
    assert rules.required_room_counts["bedroom"] == 2
    assert "open_living_kitchen" not in rules.required_room_counts


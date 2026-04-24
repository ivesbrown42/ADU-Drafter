from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from adu_drafter.contracts import (
    Agent1Input,
    Agent1Output,
    Agent2Input,
    build_agent_2_input,
)


@pytest.fixture()
def fixture_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture()
def load_fixture(fixture_dir: Path):
    def _load(name: str) -> dict[str, Any]:
        path = fixture_dir / name
        return json.loads(path.read_text(encoding="utf-8"))

    return _load


@pytest.fixture()
def load_fixture_json(fixture_dir: Path):
    def _load(scenario: str, file_name: str) -> dict[str, Any]:
        path = fixture_dir / scenario / file_name
        return json.loads(path.read_text(encoding="utf-8"))

    return _load


@pytest.fixture()
def valid_agent2_input(load_fixture_json) -> Agent2Input:
    agent1_input_payload = load_fixture_json("oversized", "agent_1_input.json")
    zone_id = agent1_input_payload["candidate_zones"][0]["zone_id"]
    program_id = agent1_input_payload["program_catalog"][0]["program_id"]
    agent1_output_payload = {
        "agent": "site-decision-agent-1",
        "version": "1.0",
        "conflict_flag": False,
        "conflict_reasons": [],
        "decision_summary": {
            "selected_strategy": "rear-left",
            "selected_zone_id": zone_id,
            "selected_program_id": program_id,
            "primary_dwelling_rear_wall_label": "PD-REAR",
        },
        "compliance_trace": [
            {
                "zone_id": zone_id,
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
            "zone_id": zone_id,
            "program_id": program_id,
            "strategy": "rear-left",
            "constraints_profile_id": "constraints-v1",
        },
        "structure_separations": [
            {
                "label": "Primary Dwelling",
                "clearance_ft": 8.0,
                "minimum_required_ft": 6.0,
                "compliant": True,
            }
        ],
        "notes": [],
    }
    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    return build_agent_2_input(agent1_input, agent1_output)


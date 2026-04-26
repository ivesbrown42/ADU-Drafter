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
    agent1_input_payload = load_fixture_json("golden", "agent_1_input.json")
    agent1_output_payload = load_fixture_json("golden", "agent_1_output.json")
    agent1_input = Agent1Input.model_validate(agent1_input_payload)
    agent1_output = Agent1Output.model_validate(agent1_output_payload)
    return build_agent_2_input(agent1_input, agent1_output)


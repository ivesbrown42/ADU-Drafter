from __future__ import annotations

import pytest

from adu_drafter.contracts import Agent1Input, ProgramCatalogEntry


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


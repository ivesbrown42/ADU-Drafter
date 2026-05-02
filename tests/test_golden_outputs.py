from __future__ import annotations

import json
from pathlib import Path

from adu_drafter.geometry_resolver import resolve_from_file


def test_geometry_resolver_input_golden_exists() -> None:
    fixture = Path("tests/fixtures/golden/geometry_resolver_input.json")
    assert fixture.exists(), "Golden resolver input fixture is missing"


def test_resolved_drawing_instructions_matches_golden() -> None:
    fixture_input = Path("tests/fixtures/golden/geometry_resolver_input.json")
    fixture_expected = Path("tests/fixtures/golden/resolved_drawing_instructions.json")

    actual = resolve_from_file(fixture_input).model_dump(mode="json")
    expected = json.loads(fixture_expected.read_text(encoding="utf-8"))

    assert actual == expected

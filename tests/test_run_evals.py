from __future__ import annotations

import json
from pathlib import Path

from scripts.run_evals import _warn_duplicate_candidate_outputs


def test_duplicate_candidate_path_warnings_empty_when_unique() -> None:
    case = {
        "case_id": "unique-case",
        "agent_2_candidate_outputs": [
            "data/eval_cases/case_happy/agent_2_output.json",
            "data/eval_cases/case_happy/agent_2_output_candidate_better.json",
        ],
    }
    assert _warn_duplicate_candidate_outputs(case) == []


def test_duplicate_candidate_path_warnings_reports_repeats() -> None:
    case = {
        "case_id": "dup-case",
        "agent_2_candidate_outputs": [
            "data/eval_cases/case_happy/agent_2_output.json",
            "data/eval_cases/case_happy/agent_2_output.json",
            "data/eval_cases/case_happy/agent_2_output_candidate_better.json",
            "data/eval_cases/case_happy/agent_2_output_candidate_better.json",
            "data/eval_cases/case_happy/agent_2_output_candidate_better.json",
        ],
    }
    duplicates = _warn_duplicate_candidate_outputs(case)
    assert duplicates == [
        "data/eval_cases/case_happy/agent_2_output.json",
        "data/eval_cases/case_happy/agent_2_output_candidate_better.json",
    ]

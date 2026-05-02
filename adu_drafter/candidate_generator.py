"""Candidate generator: emits 5 Anchor-Constrained Agent 2 prompt payloads.

Each candidate injects a distinct spatial ANCHOR_DIRECTIVE into the Agent 2
prompt so the LLM is forced to explore different room configurations.
The Best-of-N orchestrator then scores the five outputs and selects the winner.

Usage:
    python -m adu_drafter.candidate_generator \\
        --agent-2-input  data/agent_2_input.json \\
        --output-dir     data/candidates

This writes:
    data/candidates/agent_2_prompt_A.json  (bedroom → NORTH wall)
    data/candidates/agent_2_prompt_B.json  (bedroom → SOUTH wall)
    data/candidates/agent_2_prompt_C.json  (open_living_kitchen → EAST side)
    data/candidates/agent_2_prompt_D.json  (bathroom → NW corner)
    data/candidates/agent_2_prompt_E.json  (open_living_kitchen → SOUTH half)

Each file is identical to the base agent_2_input.json but with an additional
top-level field `anchor_directive` that the LLM runner must inject verbatim
into the Agent 2 system or user prompt before calling the model.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Anchor directives — each forces the LLM to begin from a different corner/
# wall, guaranteeing geometric diversity across the 5 candidates.
# ---------------------------------------------------------------------------
ANCHOR_DIRECTIVES: list[dict] = [
    {
        "candidate": "A",
        "label": "Bedroom North",
        "directive": (
            "ANCHOR CONSTRAINT A (REQUIRED): The 'bedroom' room MUST share its "
            "entire top edge with the NORTH exterior wall "
            "(i.e. room y_ft + depth_ft == footprint depth_ft). "
            "All other rooms must be placed south of the bedroom."
        ),
        "temperature_hint": 0.7,
    },
    {
        "candidate": "B",
        "label": "Bedroom South",
        "directive": (
            "ANCHOR CONSTRAINT B (REQUIRED): The 'bedroom' room MUST share its "
            "entire bottom edge with the SOUTH exterior wall "
            "(i.e. room y_ft == 0). "
            "The open_living_kitchen must be placed north of the bedroom."
        ),
        "temperature_hint": 0.7,
    },
    {
        "candidate": "C",
        "label": "Living East",
        "directive": (
            "ANCHOR CONSTRAINT C (REQUIRED): The 'open_living_kitchen' room MUST "
            "occupy the full EAST side of the footprint "
            "(i.e. room x_ft + width_ft == footprint width_ft). "
            "The bedroom must be placed to the west."
        ),
        "temperature_hint": 0.7,
    },
    {
        "candidate": "D",
        "label": "Bathroom NW Corner",
        "directive": (
            "ANCHOR CONSTRAINT D (REQUIRED): The 'bathroom' room MUST be placed "
            "in the NORTHWEST corner of the footprint "
            "(i.e. room x_ft == 0 AND room y_ft + depth_ft == footprint depth_ft). "
            "The bedroom must be immediately east or south of the bathroom."
        ),
        "temperature_hint": 0.7,
    },
    {
        "candidate": "E",
        "label": "Living South Half",
        "directive": (
            "ANCHOR CONSTRAINT E (REQUIRED): The 'open_living_kitchen' room MUST "
            "occupy the full SOUTHERN half of the footprint "
            "(i.e. y_ft == 0 and width_ft == footprint width_ft). "
            "The bedroom and bathroom must be stacked in the northern half."
        ),
        "temperature_hint": 0.7,
    },
]


def generate_candidate_prompts(
    agent_2_input_path: Path,
    output_dir: Path,
) -> list[Path]:
    """Read the base Agent 2 input and write one prompt JSON per anchor variant.

    Returns the list of written file paths in candidate order (A–E).
    """
    base = json.loads(agent_2_input_path.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for anchor in ANCHOR_DIRECTIVES:
        payload = dict(base)  # shallow copy is fine; we only add top-level keys
        payload["anchor_directive"] = anchor["directive"]
        payload["anchor_candidate"] = anchor["candidate"]
        payload["anchor_label"] = anchor["label"]
        payload["llm_temperature_hint"] = anchor["temperature_hint"]

        out_path = output_dir / f"agent_2_prompt_{anchor['candidate']}.json"
        out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[candidate_generator] Wrote {out_path}  ({anchor['label']})")
        written.append(out_path)

    return written


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate 5 Anchor-Constrained Agent 2 prompt payloads for Best-of-N selection."
    )
    parser.add_argument(
        "--agent-2-input",
        type=Path,
        required=True,
        help="Path to the base agent_2_input.json produced by the orchestrator.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/candidates"),
        help="Directory to write the 5 prompt JSON files (default: data/candidates).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        paths = generate_candidate_prompts(
            agent_2_input_path=args.agent_2_input,
            output_dir=args.output_dir,
        )
        print(f"[candidate_generator] Done. {len(paths)} prompt files written to {args.output_dir}")
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

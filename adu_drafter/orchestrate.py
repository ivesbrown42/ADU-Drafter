"""Deterministic orchestration for Agent 1 -> Agent 2 -> geometry resolver."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .contracts import (
    build_agent_2_input,
    build_geometry_resolver_input,
    ensure_sw_normalized,
    load_agent_1_input,
    load_agent_1_output,
    load_agent_2_output,
    validate_agent_1_output_against_input,
    validate_agent_2_output_against_input,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate and orchestrate Agent 1/Agent 2 handoffs."
    )
    parser.add_argument(
        "--agent-1-input",
        type=Path,
        required=True,
        help="Path to canonical agent_1_input.json payload.",
    )
    parser.add_argument(
        "--agent-1-output",
        type=Path,
        required=True,
        help="Path to canonical agent_1_output.json payload.",
    )
    parser.add_argument(
        "--agent-2-output",
        type=Path,
        default=None,
        help=(
            "Path to canonical agent_2_output.json payload. "
            "Required unless Agent 1 returns conflict_flag=true."
        ),
    )
    parser.add_argument(
        "--resolver-output",
        type=Path,
        default=Path("data/geometry_resolver_input.json"),
        help="Path to write validated geometry_resolver_input payload.",
    )
    parser.add_argument(
        "--conflict-output",
        type=Path,
        default=Path("data/orchestration_conflict.json"),
        help="Path to write conflict artifact when Agent 1 is in conflict mode.",
    )
    parser.add_argument(
        "--grid-step-ft",
        type=float,
        default=0.5,
        help="Grid step forwarded to Agent 2 input builder.",
    )
    parser.add_argument(
        "--wall-thickness-options-ft",
        nargs="+",
        type=float,
        default=[0.35, 0.5],
        help="Allowed wall thickness values forwarded to Agent 2 input builder.",
    )
    parser.add_argument(
        "--max-retry-iteration",
        type=int,
        default=3,
        help="Retry limit forwarded to Agent 2 input builder.",
    )
    parser.add_argument(
        "--input-coordinates-normalized-to-sw",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Whether upstream coordinates are normalized to SW origin.",
    )
    return parser


def run_orchestration(args: argparse.Namespace) -> int:
    print("Starting deterministic pipeline orchestration...")

    agent_1_input = load_agent_1_input(args.agent_1_input)
    agent_1_output = load_agent_1_output(args.agent_1_output)
    validate_agent_1_output_against_input(agent_1_input, agent_1_output)
    print("[1] Agent 1 artifacts validated.")

    ensure_sw_normalized(args.input_coordinates_normalized_to_sw)

    if agent_1_output.conflict_flag:
        conflict_payload = {
            "status": "conflict",
            "message": (
                "Agent 1 returned conflict_flag=true; Agent 2 and geometry resolver "
                "handoff generation were skipped."
            ),
            "agent_1_output": agent_1_output.model_dump(mode="json"),
        }
        _write_json(args.conflict_output, conflict_payload)
        print(f"[2] Conflict artifact written to {args.conflict_output}")
        return 0

    if args.agent_2_output is None:
        raise ValueError("--agent-2-output is required when Agent 1 is non-conflict")

    agent_2_input = build_agent_2_input(
        agent_1_input,
        agent_1_output,
        input_coordinates_normalized_to_sw=args.input_coordinates_normalized_to_sw,
        grid_step_ft=args.grid_step_ft,
        wall_thickness_options_ft=args.wall_thickness_options_ft,
        max_retry_iteration=args.max_retry_iteration,
    )
    print("[2] Agent 2 input built from validated Agent 1 artifacts.")

    agent_2_output = load_agent_2_output(args.agent_2_output)
    validate_agent_2_output_against_input(agent_2_input, agent_2_output)
    print("[3] Agent 2 output validated against Agent 2 input.")

    resolver_input = build_geometry_resolver_input(
        agent_2_input,
        agent_2_output,
        existing_structures_passthrough=agent_1_input.existing_structures,
    )
    _write_json(
        args.resolver_output,
        resolver_input.model_dump(mode="json"),
    )
    print(f"[4] Geometry resolver payload written to {args.resolver_output}")
    print("Pipeline orchestration complete.")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(run_orchestration(args))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()


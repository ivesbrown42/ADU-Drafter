"""Deterministic orchestration for Agent 1 -> Agent 2 -> geometry resolver."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from pydantic import ValidationError

from .contracts import (
    build_agent_2_input,
    build_conflict_geometry_resolver_input,
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


def _load_with_retries(loader, path: Path, *, retries: int, stage_name: str):
    """
    Load and validate a JSON artifact with bounded retries.
    Retries re-read from disk to allow upstream agent corrections between attempts.
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            return loader(path)
        except (ValidationError, ValueError) as exc:
            last_error = exc
            if attempt == retries:
                break
            print(
                f"[retry] {stage_name} validation failed (attempt {attempt}/{retries}): {exc}. "
                "Waiting for corrected artifact and retrying..."
            )
    assert last_error is not None
    raise ValueError(
        f"{stage_name} validation failed after {retries} attempts: {last_error}"
    ) from last_error


def _validate_with_retries(validator, *validator_args, retries: int, stage_name: str):
    """
    Run cross-contract validator with bounded retries.
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            validator(*validator_args)
            return
        except (ValidationError, ValueError) as exc:
            last_error = exc
            if attempt == retries:
                break
            print(
                f"[retry] {stage_name} contract check failed (attempt {attempt}/{retries}): {exc}. "
                "Waiting for corrected artifact and retrying..."
            )
    assert last_error is not None
    raise ValueError(
        f"{stage_name} contract check failed after {retries} attempts: {last_error}"
    ) from last_error


def _load_agent2_with_retries(
    path: Path,
    agent_2_input,
    *,
    retries: int,
    retry_poll_seconds: float,
):
    """
    Reload Agent 2 output from disk on each attempt and validate against Agent2Input.
    This enables real retry behavior when upstream LLM output is corrected between attempts.
    """
    last_error: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            candidate = load_agent_2_output(path)
            validate_agent_2_output_against_input(agent_2_input, candidate)
            return candidate
        except (ValidationError, ValueError) as exc:
            last_error = exc
            if attempt == retries:
                break
            print(
                f"[retry] Agent 2 output validation failed (attempt {attempt}/{retries}): {exc}. "
                "Waiting for corrected artifact and retrying..."
            )
            if retry_poll_seconds > 0:
                time.sleep(retry_poll_seconds)
    assert last_error is not None
    raise ValueError(
        f"Agent 2 output validation failed after {retries} attempts: {last_error}"
    ) from last_error


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
        "--schema-retries",
        type=int,
        default=3,
        help="Retry count for loading/validating Agent artifacts before hard fail.",
    )
    parser.add_argument(
        "--retry-poll-seconds",
        type=float,
        default=0.0,
        help="Sleep duration between Agent 2 retry attempts.",
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

    if not hasattr(args, "retry_poll_seconds"):
        args.retry_poll_seconds = 0.0
    if args.schema_retries < 1:
        raise ValueError("--schema-retries must be >= 1")
    if args.retry_poll_seconds < 0:
        raise ValueError("--retry-poll-seconds must be >= 0")

    agent_1_input = _load_with_retries(
        load_agent_1_input,
        args.agent_1_input,
        retries=args.schema_retries,
        stage_name="Agent 1 input",
    )
    agent_1_output = _load_with_retries(
        load_agent_1_output,
        args.agent_1_output,
        retries=args.schema_retries,
        stage_name="Agent 1 output",
    )
    _validate_with_retries(
        validate_agent_1_output_against_input,
        agent_1_input,
        agent_1_output,
        retries=args.schema_retries,
        stage_name="Agent 1 cross-contract",
    )
    print("[1] Agent 1 artifacts validated.")

    ensure_sw_normalized(args.input_coordinates_normalized_to_sw)

    if agent_1_output.conflict_flag:
        # Prevent accidental reuse of stale non-conflict resolver artifacts.
        if args.resolver_output.exists():
            args.resolver_output.unlink()
        conflict_resolver_input = build_conflict_geometry_resolver_input(
            agent_1_input,
            agent_1_output,
            input_coordinates_normalized_to_sw=args.input_coordinates_normalized_to_sw,
        )
        _write_json(args.resolver_output, conflict_resolver_input.model_dump(mode="json"))
        conflict_payload = {
            "status": "conflict",
            "message": (
                "Agent 1 returned conflict_flag=true; Agent 2 and geometry resolver "
                "handoff generation were skipped. Conflict resolver payload generated."
            ),
            "agent_1_output": agent_1_output.model_dump(mode="json"),
        }
        _write_json(args.conflict_output, conflict_payload)
        print(f"[2] Conflict artifact written to {args.conflict_output}")
        print(f"[3] Conflict geometry resolver payload written to {args.resolver_output}")
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

    agent_2_output = _load_agent2_with_retries(
        args.agent_2_output,
        agent_2_input,
        retries=args.schema_retries,
        retry_poll_seconds=args.retry_poll_seconds,
    )
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


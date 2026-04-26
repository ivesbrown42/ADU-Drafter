"""One-command deterministic pipeline runner for Agent outputs to DXF."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .drafter import generate_dxf_from_instruction_file
from .geometry_resolver import resolve_to_file
from .orchestrate import run_orchestration


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run deterministic end-to-end pipeline from agent artifacts to DXF."
    )
    parser.add_argument("--agent-1-input", type=Path, required=True)
    parser.add_argument("--agent-1-output", type=Path, required=True)
    parser.add_argument("--agent-2-output", type=Path, default=None)
    parser.add_argument(
        "--resolver-input-output",
        type=Path,
        default=Path("data/geometry_resolver_input.json"),
        help="Output path for generated GeometryResolverInput payload.",
    )
    parser.add_argument(
        "--resolved-instructions-output",
        type=Path,
        default=Path("data/resolved_drawing_instructions.json"),
        help="Output path for resolved drawing instructions.",
    )
    parser.add_argument(
        "--conflict-output",
        type=Path,
        default=Path("data/orchestration_conflict.json"),
        help="Output path for conflict artifact when Agent 1 is conflict.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("data/template.dxf"),
        help="Path to static DXF template for rendering.",
    )
    parser.add_argument(
        "--output-dxf",
        type=Path,
        default=Path("generated_adu.dxf"),
        help="Output DXF path for rendered instructions.",
    )
    parser.add_argument(
        "--floorplan-origin-x",
        type=float,
        default=100.0,
        help="X origin for enlarged floor-plan detail in modelspace.",
    )
    parser.add_argument(
        "--floorplan-origin-y",
        type=float,
        default=0.0,
        help="Y origin for enlarged floor-plan detail in modelspace.",
    )
    parser.add_argument("--grid-step-ft", type=float, default=0.5)
    parser.add_argument(
        "--wall-thickness-options-ft",
        nargs="+",
        type=float,
        default=[0.35, 0.5],
    )
    parser.add_argument("--max-retry-iteration", type=int, default=3)
    parser.add_argument(
        "--schema-retries",
        type=int,
        default=3,
        help="Schema/contract retries for orchestrator artifact validation.",
    )
    parser.add_argument(
        "--retry-poll-seconds",
        type=float,
        default=0.0,
        help="Sleep between orchestrator retry attempts.",
    )
    parser.add_argument(
        "--input-coordinates-normalized-to-sw",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def run(args: argparse.Namespace) -> int:
    floorplan_origin_x = getattr(args, "floorplan_origin_x", 100.0)
    floorplan_origin_y = getattr(args, "floorplan_origin_y", 0.0)

    orchestration_args = argparse.Namespace(
        agent_1_input=args.agent_1_input,
        agent_1_output=args.agent_1_output,
        agent_2_output=args.agent_2_output,
        resolver_output=args.resolver_input_output,
        conflict_output=args.conflict_output,
        schema_retries=args.schema_retries,
        retry_poll_seconds=args.retry_poll_seconds,
        grid_step_ft=args.grid_step_ft,
        wall_thickness_options_ft=args.wall_thickness_options_ft,
        max_retry_iteration=args.max_retry_iteration,
        input_coordinates_normalized_to_sw=args.input_coordinates_normalized_to_sw,
    )
    code = run_orchestration(orchestration_args)
    if code != 0:
        return code

    # Conflict mode: orchestration writes conflict artifact and skips resolver payload.
    if not args.resolver_input_output.exists():
        print(
            "No geometry resolver input generated (likely conflict mode). "
            f"See {args.conflict_output}."
        )
        return 0

    resolve_to_file(args.resolver_input_output, args.resolved_instructions_output)
    generate_dxf_from_instruction_file(
        instruction_path=args.resolved_instructions_output,
        template_path=args.template,
        output_path=args.output_dxf,
        floorplan_origin_x=floorplan_origin_x,
        floorplan_origin_y=floorplan_origin_y,
    )
    print(f"Wrote end-to-end DXF to {args.output_dxf}")
    return 0


def run_end_to_end(args: argparse.Namespace) -> int:
    """Alias for package-level API compatibility."""
    return run(args)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        raise SystemExit(run(args))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

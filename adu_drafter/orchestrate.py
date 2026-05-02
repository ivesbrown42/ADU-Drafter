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
from .quality_scoring import score_agent_2_layout


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
    candidate_label: str = "Agent 2 output",
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
                f"[retry] {candidate_label} validation failed (attempt {attempt}/{retries}): {exc}. "
                "Waiting for corrected artifact and retrying..."
            )
            if retry_poll_seconds > 0:
                time.sleep(retry_poll_seconds)
    assert last_error is not None
    raise ValueError(
        f"{candidate_label} validation failed after {retries} attempts: {last_error}"
    ) from last_error


def _geometry_signature(candidate) -> str:
    """Stable signature for geometry-equivalent Agent 2 candidates."""

    def _rounded(value: float) -> float:
        return round(float(value), 4)

    rooms = sorted(
        [
            {
                "room_type": room.room_type,
                "x_ft": _rounded(room.rect.x_ft),
                "y_ft": _rounded(room.rect.y_ft),
                "width_ft": _rounded(room.rect.width_ft),
                "depth_ft": _rounded(room.rect.depth_ft),
            }
            for room in candidate.rooms
        ],
        key=lambda item: (
            item["room_type"],
            item["x_ft"],
            item["y_ft"],
            item["width_ft"],
            item["depth_ft"],
        ),
    )
    walls = sorted(
        [
            {
                "kind": wall.kind,
                "sx": _rounded(wall.start_local.x_ft),
                "sy": _rounded(wall.start_local.y_ft),
                "ex": _rounded(wall.end_local.x_ft),
                "ey": _rounded(wall.end_local.y_ft),
                "thickness_ft": _rounded(wall.thickness_ft),
            }
            for wall in candidate.walls_intent
        ],
        key=lambda item: (
            item["kind"],
            item["sx"],
            item["sy"],
            item["ex"],
            item["ey"],
            item["thickness_ft"],
        ),
    )
    openings = sorted(
        [
            {
                "opening_type": opening.opening_type,
                "wall_id": opening.wall_id,
                "x_ft": _rounded(opening.anchor_local.x_ft),
                "y_ft": _rounded(opening.anchor_local.y_ft),
                "width_ft": _rounded(opening.width_ft),
            }
            for opening in candidate.openings_intent
        ],
        key=lambda item: (
            item["opening_type"],
            item["wall_id"],
            item["x_ft"],
            item["y_ft"],
            item["width_ft"],
        ),
    )
    payload = {
        "conflict_flag": bool(candidate.conflict_flag),
        "rooms": rooms,
        "walls": walls,
        "openings": openings,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _select_best_agent2_candidate(
    candidate_paths: list[Path],
    agent_2_input,
    *,
    best_of_n: int,
    retries: int,
    retry_poll_seconds: float,
    duplicate_candidate_penalty: int,
    reject_duplicate_candidates: bool,
):
    if best_of_n < 1:
        raise ValueError("--best-of-n must be >= 1")
    if not candidate_paths:
        raise ValueError("Best-of-N selection requires at least one Agent 2 candidate path")
    if duplicate_candidate_penalty < 0:
        raise ValueError("--duplicate-candidate-penalty must be >= 0")

    selection_count = min(best_of_n, len(candidate_paths))
    best_candidate = None
    best_path: Path | None = None
    best_score: float | None = None
    failures: list[str] = []
    seen_signatures: dict[str, Path] = {}

    for idx, candidate_path in enumerate(candidate_paths[:selection_count], start=1):
        label = f"Agent 2 candidate {idx}/{selection_count} ({candidate_path})"
        try:
            candidate = _load_agent2_with_retries(
                candidate_path,
                agent_2_input,
                retries=retries,
                retry_poll_seconds=retry_poll_seconds,
                candidate_label=label,
            )
            signature = _geometry_signature(candidate)
            duplicate_of: Path | None = seen_signatures.get(signature)
            if duplicate_of is None:
                seen_signatures[signature] = candidate_path

            quality = score_agent_2_layout(agent_2_input, candidate)
            base_score = float(quality.get("score", 0.0))
            score = base_score
            if duplicate_of is not None:
                if reject_duplicate_candidates:
                    failures.append(
                        f"{candidate_path}: duplicate geometry of {duplicate_of}"
                    )
                    print(
                        f"[best-of-n] Candidate {idx}/{selection_count} rejected as duplicate "
                        f"of {duplicate_of}: {candidate_path}"
                    )
                    continue
                if duplicate_candidate_penalty > 0:
                    score = max(0.0, base_score - float(duplicate_candidate_penalty))
                    print(
                        f"[best-of-n] Candidate {idx}/{selection_count} is duplicate of "
                        f"{duplicate_of}; applying duplicate penalty={duplicate_candidate_penalty} "
                        f"(base={base_score:.2f}, adjusted={score:.2f})."
                    )
                else:
                    print(
                        f"[best-of-n] Candidate {idx}/{selection_count} duplicates geometry of "
                        f"{duplicate_of}; no duplicate penalty applied."
                    )
            print(
                f"[best-of-n] Candidate {idx}/{selection_count} valid with quality score={score:.2f}: "
                f"{candidate_path}"
            )
            if best_candidate is None or best_score is None or score > best_score:
                best_candidate = candidate
                best_path = candidate_path
                best_score = score
        except ValueError as exc:
            failures.append(f"{candidate_path}: {exc}")
            print(f"[best-of-n] Candidate {idx}/{selection_count} rejected: {candidate_path} ({exc})")

    if best_candidate is None:
        raise ValueError(
            "All Agent 2 candidates failed hard validation in Best-of-N selection: "
            + "; ".join(failures)
        )

    assert best_path is not None
    assert best_score is not None
    print(
        f"[best-of-n] Selected candidate {best_path} with highest quality score={best_score:.2f}."
    )
    return best_candidate


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
            "Path to canonical single-candidate agent_2_output.json payload. "
            "Required unless --agent-2-candidate-outputs is provided or Agent 1 returns conflict_flag=true."
        ),
    )
    parser.add_argument(
        "--agent-2-candidate-outputs",
        nargs="+",
        type=Path,
        default=None,
        help=(
            "Optional list of candidate agent_2_output.json payloads for Best-of-N selection. "
            "Each candidate must pass hard validation; highest soft-quality score is selected."
        ),
    )
    parser.add_argument(
        "--best-of-n",
        type=int,
        default=1,
        help="Maximum number of Agent 2 candidates to score/select from (uses first N paths).",
    )
    parser.add_argument(
        "--duplicate-candidate-penalty",
        type=int,
        default=15,
        help=(
            "Penalty subtracted from soft score when a candidate duplicates a prior "
            "candidate's geometry signature (0 disables penalty)."
        ),
    )
    parser.add_argument(
        "--reject-duplicate-candidates",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "If true, Best-of-N skips geometry-duplicate candidates instead of scoring them."
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
    if not hasattr(args, "agent_2_candidate_outputs"):
        args.agent_2_candidate_outputs = None
    if not hasattr(args, "best_of_n"):
        args.best_of_n = 1
    if args.schema_retries < 1:
        raise ValueError("--schema-retries must be >= 1")
    if args.retry_poll_seconds < 0:
        raise ValueError("--retry-poll-seconds must be >= 0")
    if args.best_of_n < 1:
        raise ValueError("--best-of-n must be >= 1")
    if not hasattr(args, "duplicate_candidate_penalty"):
        args.duplicate_candidate_penalty = 15
    if not hasattr(args, "reject_duplicate_candidates"):
        args.reject_duplicate_candidates = False
    if args.duplicate_candidate_penalty < 0:
        raise ValueError("--duplicate-candidate-penalty must be >= 0")

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

    candidate_paths: list[Path] = list(args.agent_2_candidate_outputs or [])
    if args.agent_2_output is not None and candidate_paths:
        candidate_paths = [args.agent_2_output, *candidate_paths]
    if not candidate_paths and args.agent_2_output is None:
        raise ValueError(
            "--agent-2-output is required when Agent 1 is non-conflict unless "
            "--agent-2-candidate-outputs is provided"
        )

    agent_2_input = build_agent_2_input(
        agent_1_input,
        agent_1_output,
        input_coordinates_normalized_to_sw=args.input_coordinates_normalized_to_sw,
        grid_step_ft=args.grid_step_ft,
        wall_thickness_options_ft=args.wall_thickness_options_ft,
        max_retry_iteration=args.max_retry_iteration,
    )
    print("[2] Agent 2 input built from validated Agent 1 artifacts.")

    if candidate_paths:
        agent_2_output = _select_best_agent2_candidate(
            candidate_paths,
            agent_2_input,
            best_of_n=args.best_of_n,
            retries=args.schema_retries,
            retry_poll_seconds=args.retry_poll_seconds,
            duplicate_candidate_penalty=args.duplicate_candidate_penalty,
            reject_duplicate_candidates=args.reject_duplicate_candidates,
        )
        print("[3] Agent 2 Best-of-N selection completed.")
    else:
        agent_2_output = _load_agent2_with_retries(
            args.agent_2_output,
            agent_2_input,
            retries=args.schema_retries,
            retry_poll_seconds=args.retry_poll_seconds,
            candidate_label=f"Agent 2 output ({args.agent_2_output})",
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


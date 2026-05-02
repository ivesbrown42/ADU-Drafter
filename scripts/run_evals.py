"""Batch evaluation harness for deterministic ADU pipeline."""

from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from adu_drafter.run_pipeline import run_end_to_end
from adu_drafter.contracts import (
    Agent2Output,
    load_agent_1_input,
    load_agent_1_output,
    load_agent_2_output,
    build_agent_2_input,
)
from adu_drafter.quality_scoring import score_agent_2_layout


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_list(value: Any, field_name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"Field '{field_name}' must be a list")
    return value


def _categorize_failure(message: str) -> str:
    lower = message.lower()
    if "outside zone-local bounds" in lower or "outside selected zone bounds" in lower:
        return "bounds"
    if "overlap" in lower:
        return "overlap"
    if "grid_step_ft" in lower or "grid step" in lower:
        return "snap"
    if "host wall" in lower or "anchor_local" in lower:
        return "host-wall"
    if "validation error" in lower or "field required" in lower or "extra inputs are not permitted" in lower:
        return "schema"
    return "other"


def _attempt_run(
    *,
    case: dict[str, Any],
    attempt_index: int,
    attempt_agent2_path: Path | None,
    out_dir: Path,
    template_path: Path,
    schema_retries_per_attempt: int,
    retry_poll_seconds: float,
) -> dict[str, Any]:
    attempt_dir = out_dir / f"attempt-{attempt_index}"
    attempt_dir.mkdir(parents=True, exist_ok=True)

    resolver_input = attempt_dir / "geometry_resolver_input.json"
    resolved_instructions = attempt_dir / "resolved_drawing_instructions.json"
    conflict_artifact = attempt_dir / "conflict_artifact.json"
    output_dxf = attempt_dir / "generated_adu.dxf"
    resolved_instructions.unlink(missing_ok=True)
    conflict_artifact.unlink(missing_ok=True)
    output_dxf.unlink(missing_ok=True)

    args = argparse.Namespace(
        agent_1_input=Path(case["agent_1_input"]),
        agent_1_output=Path(case["agent_1_output"]),
        agent_2_output=attempt_agent2_path,
        agent_2_candidate_outputs=[
            Path(p)
            for p in _ensure_list(
                case.get("agent_2_candidate_outputs", []), "agent_2_candidate_outputs"
            )
        ]
        if case.get("agent_2_candidate_outputs") is not None
        else None,
        best_of_n=int(case.get("best_of_n", 1)),
        resolver_input_output=resolver_input,
        resolved_instructions_output=resolved_instructions,
        conflict_output=conflict_artifact,
        template=Path(case.get("template", str(template_path))),
        output_dxf=output_dxf,
        grid_step_ft=float(case.get("grid_step_ft", 0.5)),
        wall_thickness_options_ft=case.get("wall_thickness_options_ft", [0.35, 0.5]),
        max_retry_iteration=case.get("max_retry_iteration", 3),
        schema_retries=schema_retries_per_attempt,
        retry_poll_seconds=retry_poll_seconds,
        input_coordinates_normalized_to_sw=bool(
            case.get("input_coordinates_normalized_to_sw", True)
        ),
        floorplan_origin_x=float(case.get("floorplan_origin_x", 100.0)),
        floorplan_origin_y=float(case.get("floorplan_origin_y", 0.0)),
    )

    error_message = ""
    try:
        code = run_end_to_end(args)
        if code != 0:
            error_message = f"run_end_to_end returned non-zero code={code}"
    except Exception as exc:  # pylint: disable=broad-except
        code = 1
        error_message = f"{exc}\n{traceback.format_exc(limit=2)}"

    conflict_exists = conflict_artifact.exists()
    dxf_exists = output_dxf.exists()
    if conflict_exists:
        outcome = "conflict"
    elif dxf_exists:
        outcome = "success"
    else:
        outcome = "failure"

    quality_telemetry: dict[str, Any] | None = None
    if outcome == "success":
        try:
            agent_1_input = load_agent_1_input(Path(case["agent_1_input"]))
            agent_1_output = load_agent_1_output(Path(case["agent_1_output"]))
            agent_2_input = build_agent_2_input(
                agent_1_input,
                agent_1_output,
                input_coordinates_normalized_to_sw=bool(
                    case.get("input_coordinates_normalized_to_sw", True)
                ),
                grid_step_ft=float(case.get("grid_step_ft", 0.5)),
                wall_thickness_options_ft=case.get("wall_thickness_options_ft", [0.35, 0.5]),
                max_retry_iteration=case.get("max_retry_iteration", 3),
            )
            if attempt_agent2_path is not None:
                agent_2_output = load_agent_2_output(attempt_agent2_path)
            else:
                resolver_payload = _load_json(resolver_input)
                selected_payload = resolver_payload.get("agent_2_output")
                if not isinstance(selected_payload, dict):
                    raise ValueError(
                        "geometry_resolver_input.json missing selected 'agent_2_output' payload"
                    )
                agent_2_output = Agent2Output.model_validate(selected_payload)
            score = score_agent_2_layout(agent_2_input, agent_2_output)
            quality_telemetry = score
        except Exception as exc:  # pylint: disable=broad-except
            quality_telemetry = {
                "score": None,
                "status": "telemetry_error",
                "deductions": [],
                "notes": [f"QUALITY_SCORING_ERROR: {exc}"],
            }

    return {
        "attempt_index": attempt_index,
        "agent_2_output": str(attempt_agent2_path) if attempt_agent2_path else None,
        "code": code,
        "outcome": outcome,
        "resolver_input": str(resolver_input),
        "resolved_instructions": str(resolved_instructions),
        "conflict_artifact": str(conflict_artifact),
        "output_dxf": str(output_dxf),
        "error_message": error_message,
        "quality_telemetry": quality_telemetry,
    }


def _evaluate_case(
    case: dict[str, Any],
    *,
    output_root: Path,
    template_path: Path,
    max_attempts: int,
    schema_retries_per_attempt: int,
    retry_poll_seconds: float,
) -> dict[str, Any]:
    case_id = case["case_id"]
    expected_outcome = case.get("expected_outcome", "success")
    tier = case.get("tier", "unclassified")
    case_dir = output_root / case_id
    case_dir.mkdir(parents=True, exist_ok=True)

    attempts: list[dict[str, Any]] = []
    agent2_attempts = [
        Path(p)
        for p in _ensure_list(case.get("agent_2_attempts", []), "agent_2_attempts")
    ]
    max_attempts_case = int(case.get("max_attempts", max_attempts))
    max_attempts_case = max(1, max_attempts_case)

    for i in range(1, max_attempts_case + 1):
        attempt_agent2 = None
        if agent2_attempts:
            if i <= len(agent2_attempts):
                attempt_agent2 = agent2_attempts[i - 1]
            else:
                attempt_agent2 = agent2_attempts[-1]

        attempt = _attempt_run(
            case=case,
            attempt_index=i,
            attempt_agent2_path=attempt_agent2,
            out_dir=case_dir,
            template_path=template_path,
            schema_retries_per_attempt=schema_retries_per_attempt,
            retry_poll_seconds=retry_poll_seconds,
        )
        attempts.append(attempt)

        # Stop once we got an explicit resolved outcome from pipeline.
        if attempt["outcome"] in {"success", "conflict"}:
            break

    final_attempt = attempts[-1]
    final_outcome = final_attempt["outcome"]
    passed = final_outcome == expected_outcome

    failure_nodes: list[str] = []
    for attempt in attempts:
        msg = attempt.get("error_message", "")
        if msg:
            failure_nodes.append(_categorize_failure(msg))

    case_result = {
        "case_id": case_id,
        "tier": tier,
        "expected_outcome": expected_outcome,
        "final_outcome": final_outcome,
        "passed": passed,
        "attempts_used": len(attempts),
        "attempts": attempts,
        "failure_nodes": failure_nodes,
    }
    (case_dir / "case_result.json").write_text(
        json.dumps(case_result, indent=2), encoding="utf-8"
    )
    return case_result


def _summary(results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(results)
    if total == 0:
        return {
            "total_cases": 0,
            "first_pass_success_rate": 0.0,
            "post_retry_success_rate": 0.0,
            "conflict_rate_true_negatives": 0.0,
            "hard_failure_rate": 0.0,
            "average_retries_per_success": 0.0,
            "top_failure_nodes": {},
            "tier_breakdown": {},
        }

    first_pass_successes = sum(
        1 for r in results if r["passed"] and r["attempts_used"] == 1
    )
    post_retry_successes = sum(1 for r in results if r["passed"])
    hard_failures = sum(1 for r in results if r["final_outcome"] == "failure")

    expected_conflicts = [r for r in results if r["expected_outcome"] == "conflict"]
    true_negative_conflicts = [
        r for r in expected_conflicts if r["final_outcome"] == "conflict"
    ]
    conflict_rate = (
        len(true_negative_conflicts) / len(expected_conflicts)
        if expected_conflicts
        else 0.0
    )

    retries_for_successes = [
        r["attempts_used"] - 1 for r in results if r["passed"]
    ]
    avg_retries = mean(retries_for_successes) if retries_for_successes else 0.0

    scored_attempts: list[dict[str, Any]] = []
    soft_fail_codes: Counter[str] = Counter()
    for r in results:
        attempts = r.get("attempts", [])
        if not attempts:
            continue
        telemetry = attempts[-1].get("quality_telemetry")
        if not isinstance(telemetry, dict):
            continue
        if telemetry.get("score") is None:
            continue
        scored_attempts.append(telemetry)
        for deduction in telemetry.get("deductions", []):
            code = deduction.get("code")
            if isinstance(code, str):
                soft_fail_codes[code] += 1

    avg_quality_score = (
        mean(float(t["score"]) for t in scored_attempts)
        if scored_attempts
        else 0.0
    )
    scored_case_count = len(scored_attempts)

    failure_counts = Counter()
    for r in results:
        failure_counts.update(r["failure_nodes"])

    tiers: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "passed": 0, "success": 0, "conflict": 0, "failure": 0}
    )
    for r in results:
        t = tiers[r["tier"]]
        t["total"] += 1
        t["passed"] += int(r["passed"])
        t[r["final_outcome"]] += 1

    return {
        "total_cases": total,
        "first_pass_success_rate": first_pass_successes / total,
        "post_retry_success_rate": post_retry_successes / total,
        "conflict_rate_true_negatives": conflict_rate,
        "hard_failure_rate": hard_failures / total,
        "average_retries_per_success": avg_retries,
        "top_failure_nodes": dict(failure_counts.most_common()),
        "quality_telemetry": {
            "scored_case_count": scored_case_count,
            "average_score": avg_quality_score,
            "top_deduction_codes": dict(soft_fail_codes.most_common()),
        },
        "tier_breakdown": tiers,
    }


def _write_csv(results: list[dict[str, Any]], output_csv: Path) -> None:
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "case_id",
                "tier",
                "expected_outcome",
                "final_outcome",
                "passed",
                "attempts_used",
                "first_failure_node",
                "quality_score",
                "quality_status",
            ],
        )
        writer.writeheader()
        for r in results:
            last_attempt = r["attempts"][-1] if r.get("attempts") else None
            quality = (
                last_attempt.get("quality_telemetry")
                if isinstance(last_attempt, dict)
                else None
            )
            writer.writerow(
                {
                    "case_id": r["case_id"],
                    "tier": r["tier"],
                    "expected_outcome": r["expected_outcome"],
                    "final_outcome": r["final_outcome"],
                    "passed": r["passed"],
                    "attempts_used": r["attempts_used"],
                    "first_failure_node": r["failure_nodes"][0] if r["failure_nodes"] else "",
                    "quality_score": quality.get("score", "") if isinstance(quality, dict) else "",
                    "quality_status": quality.get("status", "") if isinstance(quality, dict) else "",
                }
            )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run batch evaluation corpus.")
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="Path to eval_corpus.json file.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/eval_reports/latest"),
        help="Directory for per-case artifacts and summary reports.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("data/template.dxf"),
        help="Default template.dxf path (overridable per case).",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=3,
        help="Max harness-level attempts per case (overridable per case).",
    )
    parser.add_argument(
        "--schema-retries-per-attempt",
        type=int,
        default=1,
        help="Schema/contract retries per single attempt invocation.",
    )
    parser.add_argument(
        "--retry-poll-seconds",
        type=float,
        default=0.0,
        help="Sleep seconds between retry polls in orchestrator.",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    corpus = _ensure_list(_load_json(args.corpus), "corpus")
    out_dir = args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    case_results: list[dict[str, Any]] = []
    for case in corpus:
        if not isinstance(case, dict):
            raise ValueError("Each corpus item must be an object")
        if "case_id" not in case:
            raise ValueError("Each corpus case requires case_id")
        if "agent_1_input" not in case or "agent_1_output" not in case:
            raise ValueError(f"Case '{case.get('case_id', '?')}' missing agent_1_input/output")

        result = _evaluate_case(
            case,
            output_root=out_dir / "cases",
            template_path=args.template,
            max_attempts=args.max_attempts,
            schema_retries_per_attempt=args.schema_retries_per_attempt,
            retry_poll_seconds=args.retry_poll_seconds,
        )
        case_results.append(result)

    summary = _summary(case_results)
    report = {"summary": summary, "cases": case_results}

    report_json = out_dir / "eval_report.json"
    report_csv = out_dir / "eval_report.csv"
    report_json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    _write_csv(case_results, report_csv)

    print(f"Wrote evaluation JSON report: {report_json}")
    print(f"Wrote evaluation CSV report:  {report_csv}")
    print(
        "Summary: "
        f"first-pass={summary['first_pass_success_rate']:.2%}, "
        f"post-retry={summary['post_retry_success_rate']:.2%}, "
        f"hard-failure={summary['hard_failure_rate']:.2%}"
    )
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    raise SystemExit(run(args))


if __name__ == "__main__":
    main()


"""Generate semantic-jitter Agent 2 prompt payloads for Best-of-N runs."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from adu_drafter.contracts import Agent2Input


@dataclass(frozen=True)
class AnchorVariation:
    directive_id: str
    directive_text: str
    anchor_constraints: list[dict[str, Any]]


def _cardinal_walls(footprint_width_ft: float, footprint_depth_ft: float) -> dict[str, dict[str, Any]]:
    return {
        "north": {
            "line_local_ft": [[0.0, footprint_depth_ft], [footprint_width_ft, footprint_depth_ft]],
            "axis": "y",
            "constant_ft": footprint_depth_ft,
        },
        "south": {
            "line_local_ft": [[0.0, 0.0], [footprint_width_ft, 0.0]],
            "axis": "y",
            "constant_ft": 0.0,
        },
        "east": {
            "line_local_ft": [[footprint_width_ft, 0.0], [footprint_width_ft, footprint_depth_ft]],
            "axis": "x",
            "constant_ft": footprint_width_ft,
        },
        "west": {
            "line_local_ft": [[0.0, 0.0], [0.0, footprint_depth_ft]],
            "axis": "x",
            "constant_ft": 0.0,
        },
    }


def _coerce_agent2_input(agent_2_input: Agent2Input | dict[str, Any]) -> Agent2Input:
    if isinstance(agent_2_input, Agent2Input):
        return agent_2_input
    if not isinstance(agent_2_input, dict):
        raise ValueError("agent_2_input must be Agent2Input or dict")
    try:
        return Agent2Input.model_validate(agent_2_input)
    except Exception:
        # Allow GeometryResolverInput-like payloads by extracting the Agent2Input subset.
        subset_keys = (
            "agent_1_output",
            "site_context",
            "selected_zone",
            "selected_program",
            "design_rules",
            "layout_rules",
        )
        subset_payload = {
            key: agent_2_input[key]
            for key in subset_keys
            if key in agent_2_input
        }
        return Agent2Input.model_validate(subset_payload)


def load_agent2_input_for_prompt_builder(path: Path) -> Agent2Input:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return _coerce_agent2_input(payload)


def build_anchor_variations(agent_2_input: Agent2Input | dict[str, Any]) -> list[AnchorVariation]:
    model = _coerce_agent2_input(agent_2_input)
    footprint_width_ft = model.selected_program.footprint_width_ft
    footprint_depth_ft = model.selected_program.footprint_depth_ft
    east_half_min_x_ft = round(footprint_width_ft / 2.0, 4)
    south_half_depth_ft = round(footprint_depth_ft / 2.0, 4)
    north_half_min_y_ft = south_half_depth_ft

    return [
        AnchorVariation(
            directive_id="anchor_north_bedroom",
            directive_text="CRITICAL: The bedroom MUST touch the NORTH exterior wall.",
            anchor_constraints=[{"room_type": "bedroom", "must_touch_wall": "north"}],
        ),
        AnchorVariation(
            directive_id="anchor_south_bedroom",
            directive_text="CRITICAL: The bedroom MUST touch the SOUTH exterior wall.",
            anchor_constraints=[{"room_type": "bedroom", "must_touch_wall": "south"}],
        ),
        AnchorVariation(
            directive_id="anchor_east_open_living_kitchen",
            directive_text=(
                "CRITICAL: The open_living_kitchen MUST occupy the full EAST side "
                "of the footprint."
            ),
            anchor_constraints=[
                {
                    "room_type": "open_living_kitchen",
                    "must_occupy_region_local_ft": {
                        "x_min_ft": east_half_min_x_ft,
                        "x_max_ft": footprint_width_ft,
                        "y_min_ft": 0.0,
                        "y_max_ft": footprint_depth_ft,
                    },
                }
            ],
        ),
        AnchorVariation(
            directive_id="anchor_nw_bathroom",
            directive_text="CRITICAL: The bathroom MUST be anchored to the NW corner.",
            anchor_constraints=[
                {
                    "room_type": "bathroom",
                    "must_touch_wall": "north",
                    "must_touch_wall_secondary": "west",
                    "must_occupy_region_local_ft": {
                        "x_min_ft": 0.0,
                        "x_max_ft": east_half_min_x_ft,
                        "y_min_ft": north_half_min_y_ft,
                        "y_max_ft": footprint_depth_ft,
                    },
                }
            ],
        ),
        AnchorVariation(
            directive_id="anchor_southern_half_living",
            directive_text=(
                "CRITICAL: The open_living_kitchen MUST occupy the entire SOUTHERN half "
                "of the footprint."
            ),
            anchor_constraints=[
                {
                    "room_type": "open_living_kitchen",
                    "must_occupy_region_local_ft": {
                        "x_min_ft": 0.0,
                        "x_max_ft": footprint_width_ft,
                        "y_min_ft": 0.0,
                        "y_max_ft": south_half_depth_ft,
                    },
                }
            ],
        ),
    ]


def build_candidate_prompt_payloads(
    agent_2_input: Agent2Input | dict[str, Any],
    *,
    candidate_count: int = 5,
    system_prompt_path: Path = Path("prompts/agent-2-adu-designer.md"),
    temperature: float = 0.7,
    top_p: float = 0.9,
    layout_jitter_seed: str | None = None,
) -> list[dict[str, Any]]:
    if candidate_count < 1:
        raise ValueError("candidate_count must be >= 1")

    model = _coerce_agent2_input(agent_2_input)
    cardinal_walls = _cardinal_walls(
        model.selected_program.footprint_width_ft,
        model.selected_program.footprint_depth_ft,
    )
    variations = build_anchor_variations(model)
    selected_variations = variations[: min(candidate_count, len(variations))]

    payloads: list[dict[str, Any]] = []
    for idx, variation in enumerate(selected_variations, start=1):
        jitter_seed = (
            f"{layout_jitter_seed}:{variation.directive_id}:{idx}"
            if layout_jitter_seed
            else variation.directive_id
        )
        payloads.append(
            {
                "candidate_id": f"candidate_{idx}",
                "generation_config": {
                    "temperature": temperature,
                    "top_p": top_p,
                    "response_format": "json_object",
                },
                "system_prompt_path": str(system_prompt_path),
                "semantic_jitter": {
                    "strategy": "anchor_constraint",
                    "directive_id": variation.directive_id,
                    "directive_text": variation.directive_text,
                    "anchor_constraints": variation.anchor_constraints,
                    "layout_jitter_seed": jitter_seed,
                },
                "anchor_context": {
                    "cardinal_walls": cardinal_walls,
                },
                "agent_2_input": model.model_dump(mode="json"),
            }
        )
    return payloads


def write_candidate_prompt_payloads(payloads: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {"candidates": []}

    for idx, payload in enumerate(payloads, start=1):
        directive_id = payload["semantic_jitter"]["directive_id"]
        suffix = directive_id.replace("anchor_", "")
        path = output_dir / f"agent2_candidate_prompt_{idx}_{suffix}.json"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        manifest["candidates"].append(
            {
                "candidate_id": payload["candidate_id"],
                "path": str(path),
                "directive_id": directive_id,
                "directive_text": payload["semantic_jitter"]["directive_text"],
            }
        )

    manifest_path = output_dir / "agent2_candidate_prompt_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Generate semantic-jitter Agent 2 prompt payloads using anchor constraints."
        )
    )
    parser.add_argument(
        "--agent-2-input",
        type=Path,
        required=True,
        help=(
            "Path to Agent2Input JSON payload. GeometryResolverInput-like payloads are "
            "also accepted if they contain the Agent2Input subset keys."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/agent2_candidate_prompts"),
        help="Directory to write candidate prompt payload JSON files.",
    )
    parser.add_argument(
        "--system-prompt-path",
        type=Path,
        default=Path("prompts/agent-2-adu-designer.md"),
        help="Path to Agent 2 system prompt markdown.",
    )
    parser.add_argument(
        "--candidate-count",
        type=int,
        default=5,
        help="Number of candidate payloads to emit (max 5 for anchor strategy).",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.7,
        help="Sampling temperature for upstream LLM call metadata.",
    )
    parser.add_argument(
        "--top-p",
        type=float,
        default=0.9,
        help="Top-p sampling value for upstream LLM call metadata.",
    )
    parser.add_argument(
        "--layout-jitter-seed",
        type=str,
        default=None,
        help="Optional seed prefix embedded per-candidate to trace semantic jitter lineage.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.temperature < 0:
        raise ValueError("--temperature must be >= 0")
    if not (0 < args.top_p <= 1):
        raise ValueError("--top-p must be within (0, 1]")
    if args.candidate_count < 1:
        raise ValueError("--candidate-count must be >= 1")

    agent_2_input = load_agent2_input_for_prompt_builder(args.agent_2_input)
    payloads = build_candidate_prompt_payloads(
        agent_2_input,
        candidate_count=args.candidate_count,
        system_prompt_path=args.system_prompt_path,
        temperature=args.temperature,
        top_p=args.top_p,
        layout_jitter_seed=args.layout_jitter_seed,
    )
    write_candidate_prompt_payloads(payloads, args.output_dir)
    print(f"Wrote {len(payloads)} Agent 2 candidate prompt payloads to {args.output_dir}")


if __name__ == "__main__":
    main()

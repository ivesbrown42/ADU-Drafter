"""End-to-end 2D ADU pipeline orchestration entrypoint."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from shapely.geometry import mapping

from .drafter import generate_dxf_from_brief
from .geometry_engine import compute_true_buildable_area, validate_design_brief_inside_area
from .models import ADUDesignBrief, SiteInput


def load_site_input(path: Path) -> SiteInput:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return SiteInput.model_validate(payload)


def load_design_brief(path: Path) -> ADUDesignBrief:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ADUDesignBrief.model_validate(payload)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a 2D ADU floor plan DXF.")
    parser.add_argument(
        "--site-input",
        type=Path,
        default=Path("data/site_input.json"),
        help="Path to SiteInput JSON file.",
    )
    parser.add_argument("--site", type=Path, dest="site_input", help=argparse.SUPPRESS)
    parser.add_argument(
        "--design-brief",
        type=Path,
        default=Path("data/manual_design_brief.json"),
        help="Path to ADU_Design_Brief JSON file (LLM output contract).",
    )
    parser.add_argument("--brief", type=Path, dest="design_brief", help=argparse.SUPPRESS)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("data/template.dxf"),
        help="Path to static block library DXF template.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("generated_adu.dxf"),
        help="Output DXF path.",
    )
    parser.add_argument(
        "--buildable-geojson",
        type=Path,
        default=None,
        help="Optional path to write buildable-area polygon as GeoJSON for debug/LLM context.",
    )
    return parser


def run_pipeline(
    *,
    site_input_path: Path,
    design_brief_path: Path,
    template_path: Path,
    output_path: Path,
    buildable_geojson_path: Path | None = None,
) -> None:
    site = load_site_input(site_input_path)
    brief = load_design_brief(design_brief_path)

    buildable_area = compute_true_buildable_area(site)
    qa = validate_design_brief_inside_area(brief, buildable_area)
    if not qa.is_valid:
        joined = "; ".join(qa.messages)
        raise ValueError(f"QA gate failed: {joined}")

    if buildable_geojson_path is not None:
        feature = {
            "type": "Feature",
            "geometry": mapping(buildable_area),
            "properties": {"name": "true_buildable_area"},
        }
        buildable_geojson_path.write_text(json.dumps(feature, indent=2), encoding="utf-8")

    generate_dxf_from_brief(brief=brief, template_path=template_path, output_path=output_path)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    run_pipeline(
        site_input_path=args.site_input,
        design_brief_path=args.design_brief,
        template_path=args.template,
        output_path=args.output,
        buildable_geojson_path=args.buildable_geojson,
    )


if __name__ == "__main__":
    main()

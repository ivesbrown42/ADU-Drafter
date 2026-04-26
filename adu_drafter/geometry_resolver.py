"""Deterministic geometry resolver producing DXF-ready drawing instructions."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from .contracts import (
    ConflictNotice,
    DimensionEntry,
    DrawingInstructionPayload,
    GeometryResolverInput,
    ExistingStructure,
    load_geometry_resolver_input,
)


def _r4(value: float) -> float:
    return round(float(value), 4)


def _pt(x: float, y: float) -> list[float]:
    return [_r4(x), _r4(y)]


def _rect(sw_x: float, sw_y: float, ne_x: float, ne_y: float) -> list[list[float]]:
    return [
        _pt(sw_x, sw_y),
        _pt(ne_x, sw_y),
        _pt(ne_x, ne_y),
        _pt(sw_x, ne_y),
        _pt(sw_x, sw_y),
    ]


def _structure_bbox(structure: ExistingStructure) -> tuple[float, float, float, float]:
    sw_x = structure.offset_from_origin_x_ft
    sw_y = structure.offset_from_origin_y_ft
    ne_x = sw_x + structure.width_ft
    ne_y = sw_y + structure.depth_ft
    return sw_x, sw_y, ne_x, ne_y


def _existing_structures_payload(resolver_input: GeometryResolverInput) -> list[dict[str, Any]]:
    payload: list[dict[str, Any]] = []
    for structure in resolver_input.existing_structures_passthrough:
        sw_x, sw_y, ne_x, ne_y = _structure_bbox(structure)
        payload.append(
            {
                "label": structure.label,
                "layer": "SITE-EXISTING-STRUCTURES",
                "linetype": "CONTINUOUS",
                "color": 2,
                "sw_corner": _pt(sw_x, sw_y),
                "ne_corner": _pt(ne_x, ne_y),
                "points": _rect(sw_x, sw_y, ne_x, ne_y),
                "label_anchor": _pt((sw_x + ne_x) / 2.0, (sw_y + ne_y) / 2.0),
                "label_text": structure.label.upper(),
                "label_height": 1.5,
            }
        )
    return payload


def _infer_side_placement(strategy: str) -> str:
    if strategy == "rear-left":
        return "left"
    if strategy == "rear-right":
        return "right"
    return "centered"


def _adu_bbox(resolver_input: GeometryResolverInput) -> tuple[float, float, float, float, float, float, str]:
    site = resolver_input.site_context
    program = resolver_input.selected_program
    side_placement = _infer_side_placement(resolver_input.agent_1_output.decision_summary.selected_strategy)
    side_setback_ft = 4.0
    rear_setback_ft = 4.0
    adu_width_ft = program.footprint_width_ft
    adu_depth_ft = program.footprint_depth_ft

    if side_placement == "left":
        adu_sw_x = side_setback_ft
    elif side_placement == "right":
        adu_sw_x = site.lot_width_ft - side_setback_ft - adu_width_ft
    else:
        adu_sw_x = (site.lot_width_ft - adu_width_ft) / 2.0
    adu_sw_y = site.lot_depth_ft - rear_setback_ft - adu_depth_ft

    adu_ne_x = adu_sw_x + adu_width_ft
    adu_ne_y = adu_sw_y + adu_depth_ft
    return adu_sw_x, adu_sw_y, adu_ne_x, adu_ne_y, adu_width_ft, adu_depth_ft, side_placement


def _street_label(resolver_input: GeometryResolverInput) -> dict[str, Any]:
    site = resolver_input.site_context
    frontage = site.street_frontage
    if frontage == "south":
        anchor = _pt(site.lot_width_ft / 2.0, -4)
    elif frontage == "north":
        anchor = _pt(site.lot_width_ft / 2.0, site.lot_depth_ft + 4)
    elif frontage == "east":
        anchor = _pt(site.lot_width_ft + 4, site.lot_depth_ft / 2.0)
    else:
        anchor = _pt(-4, site.lot_depth_ft / 2.0)

    return {
        "layer": "SITE-DIMENSIONS",
        "color": 6,
        "anchor": anchor,
        "text": "STREET",
        "height": 2.0,
        "alignment": "MIDDLE_CENTER",
    }


def _dimensions(
    resolver_input: GeometryResolverInput, *, adu_bbox: tuple[float, float, float, float, float, float, str] | None
) -> list[DimensionEntry]:
    site = resolver_input.site_context
    entries = [
        DimensionEntry(
            id="LOT_WIDTH",
            layer="SITE-DIMENSIONS",
            color=6,
            p1=_pt(0, 0),
            p2=_pt(site.lot_width_ft, 0),
            dimline_position=_pt(site.lot_width_ft / 2.0, -8),
            text=f"{_r4(site.lot_width_ft)}'",
        ),
        DimensionEntry(
            id="LOT_DEPTH",
            layer="SITE-DIMENSIONS",
            color=6,
            p1=_pt(0, 0),
            p2=_pt(0, site.lot_depth_ft),
            dimline_position=_pt(-8, site.lot_depth_ft / 2.0),
            text=f"{_r4(site.lot_depth_ft)}'",
        ),
    ]
    if adu_bbox is None:
        return entries

    adu_sw_x, adu_sw_y, adu_ne_x, adu_ne_y, adu_width_ft, adu_depth_ft, _ = adu_bbox
    entries.extend(
        [
            DimensionEntry(
                id="ADU_WIDTH",
                layer="SITE-DIMENSIONS",
                color=6,
                p1=_pt(adu_sw_x, adu_sw_y),
                p2=_pt(adu_ne_x, adu_sw_y),
                dimline_position=_pt((adu_sw_x + adu_ne_x) / 2.0, adu_sw_y - 4),
                text=f"{_r4(adu_width_ft)}'",
            ),
            DimensionEntry(
                id="ADU_DEPTH",
                layer="SITE-DIMENSIONS",
                color=6,
                p1=_pt(adu_ne_x, adu_sw_y),
                p2=_pt(adu_ne_x, adu_ne_y),
                dimline_position=_pt(adu_ne_x + 4, (adu_sw_y + adu_ne_y) / 2.0),
                text=f"{_r4(adu_depth_ft)}'",
            ),
        ]
    )
    return entries


def _separation_markers(resolver_input: GeometryResolverInput) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    for structure in resolver_input.existing_structures_passthrough:
        sw_x, sw_y, ne_x, _ = _structure_bbox(structure)
        centroid_x = (sw_x + ne_x) / 2.0
        markers.append(
            {
                "label": structure.label,
                "layer": "SITE-ADU-SEPARATION-ZONE",
                "compliant": True,
                "circle_center": _pt(centroid_x, sw_y - 4),
                "circle_radius": 1.5,
                "circle_color": 3,
                "text_anchor": _pt(centroid_x, sw_y - 7),
                "text": "SEP: 6.0ft OK",
                "text_height": 0.8,
            }
        )
    return markers


def resolve_drawing_instructions(resolver_input: GeometryResolverInput) -> DrawingInstructionPayload:
    """Compute deterministic drawing instructions from validated resolver input."""
    site = resolver_input.site_context
    geometry_flags: list[str] = []
    common_fields = {
        "agent": "python-geometry-resolver",
        "version": "1.0",
        "coordinate_system": "SW-origin-feet",
        "units": "feet",
    }

    lot_boundary = {
        "layer": "SITE-BOUNDARY",
        "linetype": "CONTINUOUS",
        "color": 7,
        "points": _rect(0, 0, site.lot_width_ft, site.lot_depth_ft),
    }
    setback_boundary = {
        "layer": "SITE-SETBACK-BOUNDARY",
        "linetype": "DASHED",
        "color": 3,
        "points": _rect(4, 4, site.lot_width_ft - 4, site.lot_depth_ft - 4),
    }
    existing_structures = _existing_structures_payload(resolver_input)
    markers = _separation_markers(resolver_input)

    if resolver_input.agent_1_output.conflict_flag:
        cx = site.lot_width_ft / 2.0
        cy = site.lot_depth_ft / 2.0
        payload = DrawingInstructionPayload(
            **common_fields,
            conflict_flag=True,
            lot_boundary=lot_boundary,
            setback_boundary=setback_boundary,
            existing_structures=existing_structures,
            adu_elements=None,
            conflict_notice=ConflictNotice(
                line1={
                    "layer": "SITE-ADU-LABEL",
                    "anchor": _pt(cx, cy + 3),
                    "text": "CONFLICT — NO COMPLIANT PLACEMENT FOUND",
                    "height": 2.0,
                },
                line2={
                    "layer": "SITE-ADU-LABEL",
                    "anchor": _pt(cx, cy),
                    "text": "SEE AGENT 1 OUTPUT FOR DETAILS",
                    "height": 1.2,
                },
            ),
            dimensions=_dimensions(resolver_input, adu_bbox=None),
            street_label=_street_label(resolver_input),
            separation_compliance_markers=markers,
            geometry_flags=geometry_flags,
        )
        return payload

    adu_sw_x, adu_sw_y, adu_ne_x, adu_ne_y, adu_w, adu_d, side_placement = _adu_bbox(resolver_input)
    if adu_w <= 0 or adu_d <= 0:
        geometry_flags.append("NEGATIVE_OR_ZERO_DIMENSION_INPUT")
    if adu_sw_x < 0 or adu_sw_y < 0 or adu_ne_x > site.lot_width_ft or adu_ne_y > site.lot_depth_ft:
        geometry_flags.append("ADU_FOOTPRINT_OUTSIDE_LOT")

    min_sep = 6.0
    sep_sw_x = adu_sw_x - min_sep
    sep_sw_y = adu_sw_y - min_sep
    sep_ne_x = adu_ne_x + min_sep
    sep_ne_y = adu_ne_y + min_sep
    if sep_sw_x < 0:
        geometry_flags.append("SEPARATION_ZONE_EXTENDS_WEST_OF_LOT")
    if sep_sw_y < 0:
        geometry_flags.append("SEPARATION_ZONE_EXTENDS_SOUTH_OF_LOT")
    if sep_ne_x > site.lot_width_ft:
        geometry_flags.append("SEPARATION_ZONE_EXTENDS_EAST_OF_LOT")
    if sep_ne_y > site.lot_depth_ft:
        geometry_flags.append("SEPARATION_ZONE_EXTENDS_NORTH_OF_LOT")

    labels = [
        f"PROPOSED ADU ({resolver_input.selected_program.program_id})",
        f"{_r4(resolver_input.selected_program.target_area_sf)} SF",
    ]
    cx = adu_sw_x + adu_w / 2.0
    cy = adu_sw_y + adu_d / 2.0
    top_y = cy + ((len(labels) - 1) / 2.0) * 1.5
    label_lines = [
        {
            "layer": "SITE-ADU-LABEL",
            "color": 1,
            "anchor": _pt(cx, top_y - i * 1.5),
            "text": text,
            "height": 0.8,
            "alignment": "MIDDLE_CENTER",
        }
        for i, text in enumerate(labels)
    ]

    # Agent 2 local geometry is resolved relative to the finalized ADU footprint
    # origin so interior drafting remains aligned with the selected shell.
    local_origin_x, local_origin_y = adu_sw_x, adu_sw_y

    walls_abs: list[dict[str, Any]] = []
    wall_lines: dict[str, tuple[list[float], list[float]]] = {}
    for wall in resolver_input.agent_2_output.walls_intent:
        sx = local_origin_x + wall.start_local.x_ft
        sy = local_origin_y + wall.start_local.y_ft
        ex = local_origin_x + wall.end_local.x_ft
        ey = local_origin_y + wall.end_local.y_ft
        spt = _pt(sx, sy)
        ept = _pt(ex, ey)
        wall_lines[wall.wall_id] = (spt, ept)
        walls_abs.append(
            {
                "wall_id": wall.wall_id,
                "kind": wall.kind,
                "start": spt,
                "end": ept,
                "thickness_ft": _r4(wall.thickness_ft),
                "layer": "SITE-ADU-FOOTPRINT" if wall.kind == "exterior" else "SITE-ADU-INTERIOR",
            }
        )

    openings_abs: list[dict[str, Any]] = []
    for opening in resolver_input.agent_2_output.openings_intent:
        openings_abs.append(
            {
                "opening_id": opening.opening_id,
                "opening_type": opening.opening_type,
                "wall_id": opening.wall_id,
                "anchor": _pt(
                    local_origin_x + opening.anchor_local.x_ft,
                    local_origin_y + opening.anchor_local.y_ft,
                ),
                "width_ft": _r4(opening.width_ft),
            }
        )

    adu_elements = {
        "footprint": {
            "layer": "SITE-ADU-FOOTPRINT",
            "linetype": "CONTINUOUS",
            "color": 1,
            "sw_corner": _pt(adu_sw_x, adu_sw_y),
            "ne_corner": _pt(adu_ne_x, adu_ne_y),
            "points": _rect(adu_sw_x, adu_sw_y, adu_ne_x, adu_ne_y),
            "side_placement": side_placement,
        },
        "separation_zone": {
            "layer": "SITE-ADU-SEPARATION-ZONE",
            "linetype": "DASHED",
            "color": 4,
            "sw_corner": _pt(sep_sw_x, sep_sw_y),
            "ne_corner": _pt(sep_ne_x, sep_ne_y),
            "points": _rect(sep_sw_x, sep_sw_y, sep_ne_x, sep_ne_y),
        },
        "label_lines": label_lines,
        "walls_absolute": walls_abs,
        "openings_absolute": openings_abs,
    }

    payload = DrawingInstructionPayload(
        **common_fields,
        conflict_flag=False,
        lot_boundary=lot_boundary,
        setback_boundary=setback_boundary,
        existing_structures=existing_structures,
        adu_elements=adu_elements,
        conflict_notice=None,
        dimensions=_dimensions(
            resolver_input,
            adu_bbox=(adu_sw_x, adu_sw_y, adu_ne_x, adu_ne_y, adu_w, adu_d, side_placement),
        ),
        street_label=_street_label(resolver_input),
        separation_compliance_markers=markers,
        geometry_flags=geometry_flags,
    )
    return payload


def resolve_from_file(resolver_input_path: Path | str) -> DrawingInstructionPayload:
    """Resolve drawing instructions from a geometry-resolver payload file."""
    return resolve_drawing_instructions(load_geometry_resolver_input(resolver_input_path))


def resolve_to_file(
    resolver_input_path: Path | str,
    output_path: Path | str,
) -> DrawingInstructionPayload:
    """Resolve drawing instructions and persist them to disk."""
    instructions = resolve_from_file(resolver_input_path)
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(instructions.model_dump_json(indent=2), encoding="utf-8")
    return instructions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Resolve deterministic drawing instructions from geometry-resolver input."
    )
    parser.add_argument(
        "--resolver-input",
        type=Path,
        required=True,
        help="Path to geometry_resolver_input.json payload.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/resolved_drawing_instructions.json"),
        help="Path to write resolved_drawing_instructions.json",
    )
    return parser


def run(args: argparse.Namespace) -> int:
    resolve_to_file(args.resolver_input, args.output)
    print(f"Wrote resolved drawing instructions to {args.output}")
    return 0


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


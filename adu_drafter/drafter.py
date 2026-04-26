"""Deterministic DXF drafting engine for 2D ADU output."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import ezdxf

from .contracts import DrawingInstructionPayload, load_drawing_instruction_payload
from .models import ADUDesignBrief


SITE_BNDY_LAYER = "A-SITE-BNDY"
SITE_SETB_LAYER = "A-SITE-SETB"
SITE_EXST_LAYER = "A-SITE-EXST"
SITE_PROP_LAYER = "A-SITE-PROP"
SITE_ANNO_LAYER = "A-SITE-ANNO"
WALL_EXTR_LAYER = "A-WALL-EXTR"
WALL_INTR_LAYER = "A-WALL-INTR"
DOOR_LAYER = "A-DOOR"
ANNO_TEXT_LAYER = "A-ANNO-TEXT"
ANNO_DIMS_LAYER = "A-ANNO-DIMS"
FLOORPLAN_OFFSET_X = 100.0
FLOORPLAN_OFFSET_Y = 0.0
EXTERIOR_WALL_THICKNESS_FT = 0.5  # 6 in
INTERIOR_WALL_THICKNESS_FT = 4.0 / 12.0  # 4 in total partition


def _draw_walls(doc: ezdxf.document.Drawing, brief: ADUDesignBrief) -> None:
    msp = doc.modelspace()
    for wall in brief.walls:
        msp.add_lwpolyline(
            [(wall.start.x, wall.start.y), (wall.end.x, wall.end.y)],
            dxfattribs={
                "layer": wall.layer,
                "const_width": wall.thickness,
            },
        )


def _insert_blocks(doc: ezdxf.document.Drawing, brief: ADUDesignBrief) -> None:
    msp = doc.modelspace()
    # ezdxf may normalize block names, so resolve user contract names case-insensitively.
    block_index = {name.lower(): name for name in doc.blocks.block_names()}
    available_blocks = set(block_index.values())
    for block in brief.blocks:
        resolved_name = block_index.get(block.block_name.lower())
        if resolved_name is None:
            raise ValueError(
                f"Block '{block.block_name}' is not present in template.dxf. "
                f"Available blocks: {sorted(available_blocks)}"
            )

        msp.add_blockref(
            resolved_name,
            (block.x, block.y),
            dxfattribs={
                "layer": block.layer,
                "rotation": block.rotation,
                "xscale": block.xscale,
                "yscale": block.yscale,
            },
        )


def generate_dxf_from_brief(
    brief: ADUDesignBrief,
    *,
    template_path: Path | str,
    output_path: Path | str,
) -> Path:
    """
    Draw a validated 2D design brief into a DXF using a static block template.
    """

    template_path = Path(template_path)
    output_path = Path(output_path)

    if not template_path.exists():
        raise FileNotFoundError(
            f"Template file not found at '{template_path}'. "
            "Provide a static template.dxf with all required blocks."
        )

    doc = ezdxf.readfile(template_path)
    _draw_walls(doc, brief)
    _insert_blocks(doc, brief)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return output_path


def _ensure_layer(doc: ezdxf.document.Drawing, layer_name: str) -> None:
    if layer_name not in doc.layers:
        doc.layers.add(layer_name)


def _draw_polyline(doc: ezdxf.document.Drawing, points: list[tuple[float, float]], layer: str) -> None:
    _ensure_layer(doc, layer)
    doc.modelspace().add_lwpolyline(points, dxfattribs={"layer": layer})


def _draw_text(
    doc: ezdxf.document.Drawing,
    *,
    text: str,
    anchor: tuple[float, float],
    layer: str,
    height: float,
) -> None:
    _ensure_layer(doc, layer)
    entity = doc.modelspace().add_text(text, dxfattribs={"layer": layer, "height": height})
    entity.set_placement(anchor, align=ezdxf.enums.TextEntityAlignment.MIDDLE_CENTER)


def _translate_point(
    point: tuple[float, float], *, dx: float, dy: float
) -> tuple[float, float]:
    return (point[0] + dx, point[1] + dy)


def _translate_points(
    points: list[tuple[float, float]], *, dx: float, dy: float
) -> list[tuple[float, float]]:
    return [_translate_point(point, dx=dx, dy=dy) for point in points]


def _draw_line(
    doc: ezdxf.document.Drawing,
    *,
    p1: tuple[float, float],
    p2: tuple[float, float],
    layer: str,
) -> None:
    _ensure_layer(doc, layer)
    doc.modelspace().add_line(p1, p2, dxfattribs={"layer": layer})


def _draw_wall_segment_offset_faces(
    doc: ezdxf.document.Drawing,
    *,
    p1: tuple[float, float],
    p2: tuple[float, float],
    thickness_ft: float,
    layer: str,
    clip_bounds: tuple[float, float, float, float] | None = None,
) -> None:
    if clip_bounds is not None:
        clipped = _clip_wall_centerline_to_bounds(p1, p2, clip_bounds)
        if clipped is None:
            return
        p1, p2 = clipped

    # Render partition walls as two offset faces (2" each side for 4" total).
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    seg_len = (dx * dx + dy * dy) ** 0.5
    if seg_len == 0:
        return
    nx = -dy / seg_len
    ny = dx / seg_len
    half = thickness_ft / 2.0
    a1 = (p1[0] + nx * half, p1[1] + ny * half)
    a2 = (p2[0] + nx * half, p2[1] + ny * half)
    b1 = (p1[0] - nx * half, p1[1] - ny * half)
    b2 = (p2[0] - nx * half, p2[1] - ny * half)
    _draw_line(doc, p1=a1, p2=a2, layer=layer)
    _draw_line(doc, p1=b1, p2=b2, layer=layer)


def _clip_wall_centerline_to_bounds(
    p1: tuple[float, float],
    p2: tuple[float, float],
    bounds: tuple[float, float, float, float],
) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """Clip orthogonal centerlines to inner shell bounds to prevent bleed."""
    min_x, min_y, max_x, max_y = bounds
    x1, y1 = p1
    x2, y2 = p2

    if abs(x2 - x1) >= abs(y2 - y1):  # horizontal
        y = min(max((y1 + y2) / 2.0, min_y), max_y)
        nx1 = min(max(x1, min_x), max_x)
        nx2 = min(max(x2, min_x), max_x)
        if abs(nx2 - nx1) < 1e-9:
            return None
        return ((nx1, y), (nx2, y))

    # vertical
    x = min(max((x1 + x2) / 2.0, min_x), max_x)
    ny1 = min(max(y1, min_y), max_y)
    ny2 = min(max(y2, min_y), max_y)
    if abs(ny2 - ny1) < 1e-9:
        return None
    return ((x, ny1), (x, ny2))


def _interior_shell_bounds(
    footprint_points: list[tuple[float, float]],
    shell_thickness_ft: float,
) -> tuple[float, float, float, float] | None:
    xs = [point[0] for point in footprint_points[:-1]]
    ys = [point[1] for point in footprint_points[:-1]]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    inner_min_x = min_x + shell_thickness_ft
    inner_max_x = max_x - shell_thickness_ft
    inner_min_y = min_y + shell_thickness_ft
    inner_max_y = max_y - shell_thickness_ft
    if inner_min_x >= inner_max_x or inner_min_y >= inner_max_y:
        return None
    return (inner_min_x, inner_min_y, inner_max_x, inner_max_y)


def _draw_exterior_shell(
    doc: ezdxf.document.Drawing,
    *,
    footprint_points: list[tuple[float, float]],
    shell_thickness_ft: float = EXTERIOR_WALL_THICKNESS_FT,
) -> None:
    # Draw outer face.
    _draw_polyline(doc, footprint_points, WALL_EXTR_LAYER)
    # Draw inner face as an inset rectangle for schematic wall thickness.
    inner_bounds = _interior_shell_bounds(footprint_points, shell_thickness_ft)
    if inner_bounds is not None:
        inner_min_x, inner_min_y, inner_max_x, inner_max_y = inner_bounds
        _draw_polyline(
            doc,
            [
                (inner_min_x, inner_min_y),
                (inner_max_x, inner_min_y),
                (inner_max_x, inner_max_y),
                (inner_min_x, inner_max_y),
                (inner_min_x, inner_min_y),
            ],
            WALL_EXTR_LAYER,
        )


def _draw_site_context(doc: ezdxf.document.Drawing, instructions: DrawingInstructionPayload) -> None:
    _draw_polyline(doc, instructions.lot_boundary.points, SITE_BNDY_LAYER)
    _draw_polyline(doc, instructions.setback_boundary.points, SITE_SETB_LAYER)

    for struct in instructions.existing_structures:
        _draw_polyline(doc, struct.points, SITE_EXST_LAYER)
        _draw_text(
            doc,
            text=struct.label_text,
            anchor=struct.label_anchor,
            layer=SITE_EXST_LAYER,
            height=struct.label_height,
        )

    if instructions.adu_elements is not None:
        _draw_polyline(doc, instructions.adu_elements.footprint.points, SITE_PROP_LAYER)
        _draw_polyline(doc, instructions.adu_elements.separation_zone.points, SITE_PROP_LAYER)
        for label in instructions.adu_elements.label_lines:
            _draw_text(
                doc,
                text=label.text,
                anchor=label.anchor,
                layer=SITE_PROP_LAYER,
                height=label.height,
            )

    if instructions.conflict_notice is not None:
        _draw_text(
            doc,
            text=instructions.conflict_notice.line1.text,
            anchor=instructions.conflict_notice.line1.anchor,
            layer=SITE_ANNO_LAYER,
            height=instructions.conflict_notice.line1.height,
        )
        _draw_text(
            doc,
            text=instructions.conflict_notice.line2.text,
            anchor=instructions.conflict_notice.line2.anchor,
            layer=SITE_ANNO_LAYER,
            height=instructions.conflict_notice.line2.height,
        )

    _draw_text(
        doc,
        text=instructions.street_label.text,
        anchor=instructions.street_label.anchor,
        layer=SITE_ANNO_LAYER,
        height=instructions.street_label.height,
    )

    msp = doc.modelspace()
    for marker in instructions.separation_compliance_markers:
        _ensure_layer(doc, SITE_ANNO_LAYER)
        msp.add_circle(
            marker.circle_center,
            radius=marker.circle_radius,
            dxfattribs={"layer": SITE_ANNO_LAYER, "color": marker.circle_color},
        )
        _draw_text(
            doc,
            text=marker.text,
            anchor=marker.text_anchor,
            layer=SITE_ANNO_LAYER,
            height=marker.text_height,
        )

    for dim in instructions.dimensions:
        if dim.id not in {"LOT_WIDTH", "LOT_DEPTH"}:
            continue
        _draw_line(doc, p1=dim.p1, p2=dim.p2, layer=SITE_ANNO_LAYER)
        _draw_text(
            doc,
            text=dim.text,
            anchor=dim.dimline_position,
            layer=SITE_ANNO_LAYER,
            height=0.8,
        )

    _draw_text(
        doc,
        text="SITE PLAN",
        anchor=(instructions.lot_boundary.points[1][0] / 2.0, instructions.lot_boundary.points[2][1] + 10.0),
        layer=SITE_ANNO_LAYER,
        height=1.5,
    )


def _draw_floor_plan_detail(
    doc: ezdxf.document.Drawing,
    instructions: DrawingInstructionPayload,
    *,
    floorplan_origin_x: float = FLOORPLAN_OFFSET_X,
    floorplan_origin_y: float = FLOORPLAN_OFFSET_Y,
) -> None:
    if instructions.adu_elements is None:
        return

    footprint = instructions.adu_elements.footprint
    source_sw_x, source_sw_y = footprint.sw_corner
    dx = floorplan_origin_x - source_sw_x
    dy = floorplan_origin_y - source_sw_y

    _draw_exterior_shell(
        doc,
        footprint_points=_translate_points(footprint.points, dx=dx, dy=dy),
        shell_thickness_ft=EXTERIOR_WALL_THICKNESS_FT,
    )

    translated_footprint = _translate_points(footprint.points, dx=dx, dy=dy)
    inner_bounds = _interior_shell_bounds(
        translated_footprint, EXTERIOR_WALL_THICKNESS_FT
    )

    msp = doc.modelspace()
    for wall in instructions.adu_elements.walls_absolute:
        if wall.kind == "exterior":
            continue
        _draw_wall_segment_offset_faces(
            doc,
            p1=_translate_point(wall.start, dx=dx, dy=dy),
            p2=_translate_point(wall.end, dx=dx, dy=dy),
            thickness_ft=INTERIOR_WALL_THICKNESS_FT,
            layer=WALL_INTR_LAYER,
            clip_bounds=inner_bounds,
        )

    for opening in instructions.adu_elements.openings_absolute:
        anchor = _translate_point(opening.anchor, dx=dx, dy=dy)
        _ensure_layer(doc, DOOR_LAYER)
        msp.add_circle(anchor, radius=0.3, dxfattribs={"layer": DOOR_LAYER})

    for room in instructions.adu_elements.room_labels:
        _draw_text(
            doc,
            text=room.text,
            anchor=_translate_point(room.anchor, dx=dx, dy=dy),
            layer=ANNO_TEXT_LAYER,
            height=room.height,
        )

    for dim in instructions.dimensions:
        if dim.id not in {"ADU_WIDTH", "ADU_DEPTH"}:
            continue
        _draw_line(
            doc,
            p1=_translate_point(dim.p1, dx=dx, dy=dy),
            p2=_translate_point(dim.p2, dx=dx, dy=dy),
            layer=ANNO_DIMS_LAYER,
        )
        _draw_text(
            doc,
            text=dim.text,
            anchor=_translate_point(dim.dimline_position, dx=dx, dy=dy),
            layer=ANNO_DIMS_LAYER,
            height=0.8,
        )

    min_x = min(point[0] for point in translated_footprint)
    max_x = max(point[0] for point in translated_footprint)
    min_y = min(point[1] for point in translated_footprint)
    max_y = max(point[1] for point in translated_footprint)
    _draw_text(
        doc,
        text="ADU FLOOR PLAN",
        anchor=((min_x + max_x) / 2.0, max_y + 10.0),
        layer=ANNO_TEXT_LAYER,
        height=1.5,
    )
    if instructions.adu_elements.label_lines:
        summary_note = " | ".join(label.text for label in instructions.adu_elements.label_lines)
        _draw_text(
            doc,
            text=summary_note,
            anchor=((min_x + max_x) / 2.0, min_y - 12.0),
            layer=ANNO_TEXT_LAYER,
            height=0.8,
        )


def generate_dxf_from_instructions(
    instructions: DrawingInstructionPayload,
    *,
    template_path: Path | str,
    output_path: Path | str,
    floorplan_origin_x: float = FLOORPLAN_OFFSET_X,
    floorplan_origin_y: float = FLOORPLAN_OFFSET_Y,
) -> Path:
    """
    Render deterministic resolved drawing instructions into a DXF artifact.
    """
    template_path = Path(template_path)
    output_path = Path(output_path)
    if not template_path.exists():
        raise FileNotFoundError(
            f"Template file not found at '{template_path}'. "
            "Provide a static template.dxf with required layers/blocks."
        )

    doc = ezdxf.readfile(template_path)
    _draw_site_context(doc, instructions)
    _draw_floor_plan_detail(
        doc,
        instructions,
        floorplan_origin_x=floorplan_origin_x,
        floorplan_origin_y=floorplan_origin_y,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return output_path


def generate_dxf_from_instruction_file(
    instruction_path: Path | str,
    *,
    template_path: Path | str,
    output_path: Path | str,
    floorplan_origin_x: float = FLOORPLAN_OFFSET_X,
    floorplan_origin_y: float = FLOORPLAN_OFFSET_Y,
) -> Path:
    """Load DrawingInstructionPayload from JSON file and render DXF."""
    instructions = load_drawing_instruction_payload(instruction_path)
    return generate_dxf_from_instructions(
        instructions,
        template_path=template_path,
        output_path=output_path,
        floorplan_origin_x=floorplan_origin_x,
        floorplan_origin_y=floorplan_origin_y,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render deterministic drawing instructions into a DXF."
    )
    parser.add_argument(
        "--instructions",
        type=Path,
        required=True,
        help="Path to resolved_drawing_instructions.json payload.",
    )
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("data/template.dxf"),
        help="Path to static DXF template for rendering.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("generated_adu_from_instructions.dxf"),
        help="Output DXF path.",
    )
    parser.add_argument(
        "--floorplan-origin-x",
        type=float,
        default=FLOORPLAN_OFFSET_X,
        help=(
            "X origin for the enlarged floor-plan detail in modelspace. "
            "Site plan remains anchored at (0,0)."
        ),
    )
    parser.add_argument(
        "--floorplan-origin-y",
        type=float,
        default=FLOORPLAN_OFFSET_Y,
        help=(
            "Y origin for the enlarged floor-plan detail in modelspace. "
            "Site plan remains anchored at (0,0)."
        ),
    )
    return parser


def run(args: argparse.Namespace) -> int:
    generate_dxf_from_instruction_file(
        instruction_path=args.instructions,
        template_path=args.template,
        output_path=args.output,
        floorplan_origin_x=args.floorplan_origin_x,
        floorplan_origin_y=args.floorplan_origin_y,
    )
    print(f"Wrote DXF to {args.output}")
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

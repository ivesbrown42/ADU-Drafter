"""Deterministic DXF drafting engine for 2D ADU output."""

from __future__ import annotations

from pathlib import Path
import ezdxf

from .contracts import DrawingInstructionPayload, load_drawing_instruction_payload
from .models import ADUDesignBrief


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


def generate_dxf_from_instructions(
    instructions: DrawingInstructionPayload,
    *,
    template_path: Path | str,
    output_path: Path | str,
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
    msp = doc.modelspace()

    _draw_polyline(doc, instructions.lot_boundary.points, instructions.lot_boundary.layer)
    _draw_polyline(doc, instructions.setback_boundary.points, instructions.setback_boundary.layer)

    for struct in instructions.existing_structures:
        _draw_polyline(doc, struct.points, struct.layer)
        _draw_text(
            doc,
            text=struct.label_text,
            anchor=struct.label_anchor,
            layer=struct.layer,
            height=struct.label_height,
        )

    if instructions.adu_elements is not None:
        _draw_polyline(
            doc,
            instructions.adu_elements.footprint.points,
            instructions.adu_elements.footprint.layer,
        )
        _draw_polyline(
            doc,
            instructions.adu_elements.separation_zone.points,
            instructions.adu_elements.separation_zone.layer,
        )

        for label in instructions.adu_elements.label_lines:
            _draw_text(
                doc,
                text=label.text,
                anchor=label.anchor,
                layer=label.layer,
                height=label.height,
            )

        for wall in instructions.adu_elements.walls_absolute:
            _ensure_layer(doc, wall.layer)
            msp.add_lwpolyline(
                [wall.start, wall.end],
                dxfattribs={"layer": wall.layer, "const_width": wall.thickness_ft},
            )

        for opening in instructions.adu_elements.openings_absolute:
            _ensure_layer(doc, "SITE-ADU-OPENINGS")
            msp.add_circle(opening.anchor, radius=0.3, dxfattribs={"layer": "SITE-ADU-OPENINGS"})

    if instructions.conflict_notice is not None:
        _draw_text(
            doc,
            text=instructions.conflict_notice.line1.text,
            anchor=instructions.conflict_notice.line1.anchor,
            layer=instructions.conflict_notice.line1.layer,
            height=instructions.conflict_notice.line1.height,
        )
        _draw_text(
            doc,
            text=instructions.conflict_notice.line2.text,
            anchor=instructions.conflict_notice.line2.anchor,
            layer=instructions.conflict_notice.line2.layer,
            height=instructions.conflict_notice.line2.height,
        )

    for dim in instructions.dimensions:
        _ensure_layer(doc, dim.layer)
        msp.add_line(dim.p1, dim.p2, dxfattribs={"layer": dim.layer})
        _draw_text(
            doc,
            text=dim.text,
            anchor=dim.dimline_position,
            layer=dim.layer,
            height=0.8,
        )

    _draw_text(
        doc,
        text=instructions.street_label.text,
        anchor=instructions.street_label.anchor,
        layer=instructions.street_label.layer,
        height=instructions.street_label.height,
    )

    for marker in instructions.separation_compliance_markers:
        _ensure_layer(doc, marker.layer)
        msp.add_circle(
            marker.circle_center,
            radius=marker.circle_radius,
            dxfattribs={"layer": marker.layer, "color": marker.circle_color},
        )
        _draw_text(
            doc,
            text=marker.text,
            anchor=marker.text_anchor,
            layer=marker.layer,
            height=marker.text_height,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.saveas(output_path)
    return output_path


def generate_dxf_from_instruction_file(
    instruction_path: Path | str,
    *,
    template_path: Path | str,
    output_path: Path | str,
) -> Path:
    """Load DrawingInstructionPayload from JSON file and render DXF."""
    instructions = load_drawing_instruction_payload(instruction_path)
    return generate_dxf_from_instructions(
        instructions,
        template_path=template_path,
        output_path=output_path,
    )

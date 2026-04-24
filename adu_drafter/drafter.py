"""Deterministic DXF drafting engine for 2D ADU output."""

from __future__ import annotations

from pathlib import Path
import ezdxf

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

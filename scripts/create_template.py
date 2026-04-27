"""Create a minimal static DXF template with required ADU blocks."""

from __future__ import annotations

from pathlib import Path

import ezdxf


def ensure_layers(doc: ezdxf.document.Drawing) -> None:
    for layer_name in (
        "A-WALL",
        "A-WALL-INT",
        "A-DOOR",
        "A-FIXT",
        "A-FURN",
        "A-SITE-BNDY",
        "A-SITE-SETB",
        "A-SITE-EXST",
        "A-SITE-PROP",
        "A-SITE-ANNO",
        "A-WALL-EXTR",
        "A-WALL-INTR",
        "A-ANNO-TEXT",
        "A-ANNO-DIMS",
    ):
        if layer_name not in doc.layers:
            doc.layers.add(layer_name)


def add_block_if_missing(
    doc: ezdxf.document.Drawing, name: str
) -> ezdxf.layouts.BlockLayout:
    if name in doc.blocks.block_names():
        return doc.blocks.get(name)
    return doc.blocks.new(name=name)


def create_blocks(doc: ezdxf.document.Drawing) -> None:
    door = add_block_if_missing(doc, "DOOR_SINGLE_36")
    if len(door) == 0:
        door.add_line((0, 0), (3, 0))
        door.add_arc(center=(0, 0), radius=3, start_angle=0, end_angle=90)

    toilet = add_block_if_missing(doc, "TOILET_STANDARD")
    if len(toilet) == 0:
        toilet.add_ellipse(center=(0, 0), major_axis=(1.2, 0), ratio=0.7)
        toilet.add_line((-0.6, -1.4), (0.6, -1.4))

    island = add_block_if_missing(doc, "KITCHEN_ISLAND_SMALL")
    if len(island) == 0:
        island.add_lwpolyline(
            [(-2, -1), (2, -1), (2, 1), (-2, 1), (-2, -1)],
            close=True,
        )


def main() -> None:
    output = Path("data/template.dxf")
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = ezdxf.new(dxfversion="R2018")
    ensure_layers(doc)
    create_blocks(doc)
    doc.saveas(output)
    print(f"Wrote static template to {output}")


if __name__ == "__main__":
    main()

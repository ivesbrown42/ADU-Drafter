from __future__ import annotations

import ezdxf

from adu_drafter.drafter import generate_dxf_from_instruction_file


def _x_values_for_layer(path: str, layer: str) -> list[float]:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    xs: list[float] = []
    for entity in msp:
        if entity.dxf.layer != layer:
            continue
        if entity.dxftype() == "LWPOLYLINE":
            points = entity.get_points(format="xy")
            xs.extend(point[0] for point in points)
    return xs


def test_floorplan_offset_is_configurable(tmp_path) -> None:
    instructions = "tests/fixtures/golden/resolved_drawing_instructions.json"
    template = "data/template.dxf"

    out_default = tmp_path / "default_offset.dxf"
    out_custom = tmp_path / "custom_offset.dxf"

    generate_dxf_from_instruction_file(
        instruction_path=instructions,
        template_path=template,
        output_path=out_default,
        floorplan_origin_x=100.0,
        floorplan_origin_y=0.0,
    )
    generate_dxf_from_instruction_file(
        instruction_path=instructions,
        template_path=template,
        output_path=out_custom,
        floorplan_origin_x=240.0,
        floorplan_origin_y=0.0,
    )

    default_floorplan_xs = _x_values_for_layer(str(out_default), "A-WALL-EXTR")
    custom_floorplan_xs = _x_values_for_layer(str(out_custom), "A-WALL-EXTR")
    default_site_xs = _x_values_for_layer(str(out_default), "A-SITE-BNDY")
    custom_site_xs = _x_values_for_layer(str(out_custom), "A-SITE-BNDY")

    assert default_floorplan_xs
    assert custom_floorplan_xs
    assert min(default_floorplan_xs) == 100.0
    assert min(custom_floorplan_xs) == 240.0

    # Site geometry remains anchored at origin regardless of floorplan offset.
    assert min(default_site_xs) == 0.0
    assert min(custom_site_xs) == 0.0

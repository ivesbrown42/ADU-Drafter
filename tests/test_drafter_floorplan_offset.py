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


def _points_for_layer(path: str, layer: str) -> list[tuple[float, float]]:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    points: list[tuple[float, float]] = []
    for entity in msp:
        if entity.dxf.layer != layer:
            continue
        if entity.dxftype() == "LWPOLYLINE":
            points.extend((point[0], point[1]) for point in entity.get_points(format="xy"))
        elif entity.dxftype() == "LINE":
            points.append((entity.dxf.start.x, entity.dxf.start.y))
            points.append((entity.dxf.end.x, entity.dxf.end.y))
    return points


def _count_layer_entities(path: str, layer: str, dxftype: str | None = None) -> int:
    doc = ezdxf.readfile(path)
    msp = doc.modelspace()
    count = 0
    for entity in msp:
        if entity.dxf.layer != layer:
            continue
        if dxftype is not None and entity.dxftype() != dxftype:
            continue
        count += 1
    return count


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


def test_interior_walls_are_trimmed_to_inner_shell(tmp_path) -> None:
    instructions = "tests/fixtures/golden/resolved_drawing_instructions.json"
    template = "data/template.dxf"
    out = tmp_path / "trimmed_interior.dxf"

    generate_dxf_from_instruction_file(
        instruction_path=instructions,
        template_path=template,
        output_path=out,
        floorplan_origin_x=100.0,
        floorplan_origin_y=0.0,
    )

    interior_points = _points_for_layer(str(out), "A-WALL-INTR")
    assert interior_points, "Expected interior wall entities to be rendered"

    # For the golden 20x30 footprint at origin (100,0), 6 in shell inset bounds are:
    # x in [100.5, 119.5], y in [0.5, 29.5]
    for x, y in interior_points:
        assert 100.5 <= x <= 119.5
        assert 0.5 <= y <= 29.5


def test_interior_walls_render_as_merged_polygons(tmp_path) -> None:
    instructions = "tests/fixtures/golden/resolved_drawing_instructions.json"
    template = "data/template.dxf"
    out = tmp_path / "merged_interior.dxf"

    generate_dxf_from_instruction_file(
        instruction_path=instructions,
        template_path=template,
        output_path=out,
        floorplan_origin_x=100.0,
        floorplan_origin_y=0.0,
    )

    # Unioned polygon boundaries are emitted as polylines.
    intr_polylines = _count_layer_entities(str(out), "A-WALL-INTR", dxftype="LWPOLYLINE")
    intr_lines = _count_layer_entities(str(out), "A-WALL-INTR", dxftype="LINE")
    assert intr_polylines > 0
    assert intr_lines == 0


def test_generated_dxf_explicitly_sets_units_to_feet(tmp_path) -> None:
    instructions = "tests/fixtures/golden/resolved_drawing_instructions.json"
    template = "data/template.dxf"
    out = tmp_path / "units_feet.dxf"

    generate_dxf_from_instruction_file(
        instruction_path=instructions,
        template_path=template,
        output_path=out,
        floorplan_origin_x=100.0,
        floorplan_origin_y=0.0,
    )

    doc = ezdxf.readfile(out)
    assert doc.units == 2
    assert doc.header.get("$MEASUREMENT") == 0

from __future__ import annotations

from shapely.geometry import Point

from adu_drafter.geometry_engine import compute_true_buildable_area
from adu_drafter.models import SiteInput


def _base_payload() -> dict:
    return {
        "lot_width": 50.0,
        "lot_depth": 120.0,
        "setbacks": {
            "front": 15.0,
            "rear": 16.0,
            "left": 5.0,
            "right": 5.0,
        },
    }


def test_buildable_area_subtracts_multiple_existing_structures() -> None:
    payload = _base_payload()
    payload["existing_structures"] = [
        {
            "name": "Primary Residence",
            "x_min": 10.0,
            "y_min": 20.0,
            "x_max": 40.0,
            "y_max": 55.0,
            "separation_req": 6.0,
        },
        {
            "name": "Detached Garage",
            "x_min": 5.0,
            "y_min": 85.0,
            "x_max": 20.0,
            "y_max": 100.0,
            "separation_req": 6.0,
        },
    ]
    site = SiteInput.model_validate(payload)

    buildable = compute_true_buildable_area(site)

    # Should keep positive area and exclude each structure's buffered footprint.
    assert buildable.geom_type in {"Polygon", "MultiPolygon"}
    assert buildable.area > 0
    assert not buildable.contains(Point(25.0, 37.5))
    assert not buildable.contains(Point(12.5, 92.5))


def test_site_input_legacy_existing_house_is_normalized() -> None:
    payload = _base_payload()
    payload["existing_house"] = {
        "min_x": 10.0,
        "min_y": 20.0,
        "max_x": 40.0,
        "max_y": 55.0,
    }
    payload["separation_distance"] = 6.0

    site = SiteInput.model_validate(payload)

    assert len(site.existing_structures) == 1
    assert site.existing_structures[0].name == "Primary Residence"
    assert site.existing_structures[0].x_min == 10.0
    assert site.existing_structures[0].separation_req == 6.0

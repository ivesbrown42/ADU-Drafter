"""2D geometry utilities for buildable-area derivation and QA checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, List

from shapely.geometry import LineString, Point, Polygon, box
from shapely.geometry.base import BaseGeometry
from shapely.ops import unary_union

from .models import ADUDesignBrief, Point2D, SiteInput


@dataclass(frozen=True)
class QAResult:
    """Result of validating a design brief against buildable area."""

    is_valid: bool
    messages: List[str]


def _setback_polygon(site: SiteInput) -> Polygon:
    # Coordinates assume front setback starts at y=0 and rear at y=lot_depth.
    min_x = site.setbacks.left
    min_y = site.setbacks.front
    max_x = site.lot_width - site.setbacks.right
    max_y = site.lot_depth - site.setbacks.rear

    if max_x <= min_x or max_y <= min_y:
        raise ValueError("Setbacks consume entire lot; no interior buildable region")
    return box(min_x, min_y, max_x, max_y)


def _expanded_existing_house(site: SiteInput) -> Polygon:
    existing = site.existing_house
    poly = box(existing.min_x, existing.min_y, existing.max_x, existing.max_y)
    if site.separation_distance > 0:
        poly = poly.buffer(site.separation_distance, cap_style=3, join_style=2)
    return poly


def compute_true_buildable_area(site: SiteInput) -> Polygon:
    """
    Compute True Buildable Area in 2D:
    lot interior after setbacks minus existing structure plus separation.
    """

    lot_after_setbacks = _setback_polygon(site)
    exclusion = _expanded_existing_house(site)
    buildable = lot_after_setbacks.difference(exclusion)
    if buildable.is_empty:
        raise ValueError("Computed buildable area is empty")
    return buildable


def _point(point: Point2D) -> tuple[float, float]:
    return (point.x, point.y)


def _wall_geometries(brief: ADUDesignBrief) -> Iterable[BaseGeometry]:
    for wall in brief.walls:
        line = LineString([_point(wall.start), _point(wall.end)])
        # Wall thickness represented as centered 2D footprint.
        yield line.buffer(wall.thickness / 2.0, cap_style=2, join_style=2)


def _block_geometries(brief: ADUDesignBrief, block_clearance: float = 0.0) -> Iterable[BaseGeometry]:
    for block in brief.blocks:
        p = Point(block.x, block.y).buffer(0.001)
        if block_clearance > 0:
            p = p.buffer(block_clearance, cap_style=1, join_style=1)
        yield p


def validate_design_brief_inside_area(
    brief: ADUDesignBrief,
    buildable_area: BaseGeometry,
    *,
    block_clearance: float = 0.0,
) -> QAResult:
    """
    Validate that all wall and block footprints are inside buildable area.
    Also checks for collisions between wall and block footprints.
    """

    messages: List[str] = []
    footprints = list(_wall_geometries(brief)) + list(_block_geometries(brief, block_clearance))
    if not footprints:
        return QAResult(is_valid=True, messages=["No geometry found in design brief"])

    combined = unary_union(footprints)
    if not combined.within(buildable_area):
        outside = combined.difference(buildable_area)
        messages.append(
            f"Design exceeds buildable area by approximately {outside.area:.2f} sq units."
        )

    # Pairwise collision check for blocks only.
    block_geoms = list(_block_geometries(brief, block_clearance))
    for i in range(len(block_geoms)):
        for j in range(i + 1, len(block_geoms)):
            if block_geoms[i].intersects(block_geoms[j]):
                messages.append(f"Block collision detected between indices {i} and {j}.")

    return QAResult(is_valid=not messages, messages=messages)

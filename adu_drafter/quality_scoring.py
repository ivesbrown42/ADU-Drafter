"""Soft-rule quality scoring for Agent 2 layout telemetry.

This module intentionally does NOT enforce hard validation. It provides
advisory scoring aligned to the ADU spatial heuristics framework so eval runs
can measure layout quality without affecting retry/failure behavior.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import mean
from typing import Any, Callable

from .contracts import Agent2Input, Agent2Output, LocalPoint, LocalRect, OpeningIntent, RoomIntent

EPS = 1e-6


@dataclass(frozen=True)
class SoftScoringRule:
    """Registry entry for a single soft-scoring rule."""

    code: str
    description: str
    apply: Callable[["SoftScoringContext", "SoftScoringAccumulator"], None]


@dataclass
class SoftScoringAccumulator:
    """Mutable scoring accumulator shared across soft rules."""

    deductions: list[dict[str, Any]] = field(default_factory=list)

    def add_deduction(self, code: str, penalty: int, description: str) -> None:
        self.deductions.append(
            {"code": code, "penalty": penalty, "description": description}
        )


@dataclass
class SoftScoringContext:
    """Precomputed context shared by soft-scoring rules."""

    agent_input: Agent2Input
    agent_output: Agent2Output
    footprint_width: float
    footprint_depth: float
    footprint_area: float
    bedroom_count: int
    rooms: list[RoomIntent]
    bedrooms: list[RoomIntent]
    bathrooms: list[RoomIntent]
    kitchens: list[RoomIntent]
    livings: list[RoomIntent]
    open_living_kitchens: list[RoomIntent]
    plumbing_rooms: list[RoomIntent]
    exterior_walls: list[Any]
    interior_walls: list[Any]
    doors: list[OpeningIntent]
    room_groups_by_type: dict[str, list[RoomIntent]]
    total_room_area: float
    room_utilization: float
    unassigned_pct: float
    aspect_ratio: float
    recommended_open_plan: bool
    room_rectangularity_ratio: float
    room_axis_convex: bool

    @property
    def living_zone_rooms(self) -> list[RoomIntent]:
        return (
            self.open_living_kitchens
            if self.open_living_kitchens
            else (self.livings + self.kitchens)
        )

    @property
    def long_axis(self) -> str:
        return "x" if self.footprint_width >= self.footprint_depth else "y"

    def opening_touches_room_types(self, opening: OpeningIntent) -> set[str]:
        return _opening_touches_room_types(opening, self.rooms)


def _room_area(room: RoomIntent) -> float:
    return room.rect.width_ft * room.rect.depth_ft


def _point_on_room_boundary(rect: LocalRect, point: LocalPoint) -> bool:
    x = point.x_ft
    y = point.y_ft
    on_left = abs(x - rect.x_ft) <= EPS and rect.y_ft - EPS <= y <= rect.max_y + EPS
    on_right = abs(x - rect.max_x) <= EPS and rect.y_ft - EPS <= y <= rect.max_y + EPS
    on_bottom = abs(y - rect.y_ft) <= EPS and rect.x_ft - EPS <= x <= rect.max_x + EPS
    on_top = abs(y - rect.max_y) <= EPS and rect.x_ft - EPS <= x <= rect.max_x + EPS
    return on_left or on_right or on_bottom or on_top


def _room_exterior_edge_count(
    rect: LocalRect, footprint_width_ft: float, footprint_depth_ft: float
) -> int:
    count = 0
    if abs(rect.x_ft - 0.0) <= EPS:
        count += 1
    if abs(rect.max_x - footprint_width_ft) <= EPS:
        count += 1
    if abs(rect.y_ft - 0.0) <= EPS:
        count += 1
    if abs(rect.max_y - footprint_depth_ft) <= EPS:
        count += 1
    return count


def _rects_connected(a: LocalRect, b: LocalRect) -> bool:
    overlap_w = min(a.max_x, b.max_x) - max(a.x_ft, b.x_ft)
    overlap_h = min(a.max_y, b.max_y) - max(a.y_ft, b.y_ft)
    return overlap_w >= -EPS and overlap_h >= -EPS


def _group_centroid_axis(rooms: list[RoomIntent], *, axis: str) -> float | None:
    if not rooms:
        return None
    values = []
    for room in rooms:
        cx = room.rect.x_ft + room.rect.width_ft / 2.0
        cy = room.rect.y_ft + room.rect.depth_ft / 2.0
        values.append(cx if axis == "x" else cy)
    return mean(values)


def _opening_touches_room_types(opening: OpeningIntent, rooms: list[RoomIntent]) -> set[str]:
    touched: set[str] = set()
    for room in rooms:
        if _point_on_room_boundary(room.rect, opening.anchor_local):
            touched.add(room.room_type)
    return touched


def _shared_boundary_partition_exists(
    rooms_a: list[RoomIntent], rooms_b: list[RoomIntent], interior_walls: list[Any]
) -> bool:
    for room_a in rooms_a:
        for room_b in rooms_b:
            # Vertical shared boundary
            if abs(room_a.rect.max_x - room_b.rect.x_ft) <= EPS or abs(
                room_b.rect.max_x - room_a.rect.x_ft
            ) <= EPS:
                boundary_x = room_a.rect.max_x if abs(room_a.rect.max_x - room_b.rect.x_ft) <= EPS else room_b.rect.max_x
                span_y1 = max(room_a.rect.y_ft, room_b.rect.y_ft)
                span_y2 = min(room_a.rect.max_y, room_b.rect.max_y)
                if span_y2 - span_y1 > EPS:
                    for wall in interior_walls:
                        if abs(wall.start_local.x_ft - wall.end_local.x_ft) <= EPS and abs(
                            wall.start_local.x_ft - boundary_x
                        ) <= EPS:
                            wy1 = min(wall.start_local.y_ft, wall.end_local.y_ft)
                            wy2 = max(wall.start_local.y_ft, wall.end_local.y_ft)
                            if min(wy2, span_y2) - max(wy1, span_y1) > EPS:
                                return True
            # Horizontal shared boundary
            if abs(room_a.rect.max_y - room_b.rect.y_ft) <= EPS or abs(
                room_b.rect.max_y - room_a.rect.y_ft
            ) <= EPS:
                boundary_y = room_a.rect.max_y if abs(room_a.rect.max_y - room_b.rect.y_ft) <= EPS else room_b.rect.max_y
                span_x1 = max(room_a.rect.x_ft, room_b.rect.x_ft)
                span_x2 = min(room_a.rect.max_x, room_b.rect.max_x)
                if span_x2 - span_x1 > EPS:
                    for wall in interior_walls:
                        if abs(wall.start_local.y_ft - wall.end_local.y_ft) <= EPS and abs(
                            wall.start_local.y_ft - boundary_y
                        ) <= EPS:
                            wx1 = min(wall.start_local.x_ft, wall.end_local.x_ft)
                            wx2 = max(wall.start_local.x_ft, wall.end_local.x_ft)
                            if min(wx2, span_x2) - max(wx1, span_x1) > EPS:
                                return True
    return False


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals, key=lambda pair: pair[0]):
        if not merged or start > merged[-1][1] + EPS:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def _compute_layout_shape_metrics(rooms: list[RoomIntent]) -> tuple[float, float, bool]:
    """Return (union_area, rectangularity_ratio, axis_convex)."""
    if not rooms:
        return 0.0, 1.0, True

    rects = [room.rect for room in rooms]
    min_x = min(rect.x_ft for rect in rects)
    max_x = max(rect.max_x for rect in rects)
    min_y = min(rect.y_ft for rect in rects)
    max_y = max(rect.max_y for rect in rects)
    bbox_area = max(0.0, (max_x - min_x)) * max(0.0, (max_y - min_y))

    x_breaks = sorted({rect.x_ft for rect in rects} | {rect.max_x for rect in rects})
    y_breaks = sorted({rect.y_ft for rect in rects} | {rect.max_y for rect in rects})

    union_area = 0.0
    has_multi_span_x = False
    for idx in range(len(x_breaks) - 1):
        x1 = x_breaks[idx]
        x2 = x_breaks[idx + 1]
        slab_width = x2 - x1
        if slab_width <= EPS:
            continue
        intervals = [
            (rect.y_ft, rect.max_y)
            for rect in rects
            if rect.x_ft < x2 - EPS and rect.max_x > x1 + EPS
        ]
        merged = _merge_intervals(intervals)
        if len(merged) > 1:
            has_multi_span_x = True
        covered_height = sum(end - start for start, end in merged)
        union_area += slab_width * covered_height

    has_multi_span_y = False
    for idx in range(len(y_breaks) - 1):
        y1 = y_breaks[idx]
        y2 = y_breaks[idx + 1]
        slab_depth = y2 - y1
        if slab_depth <= EPS:
            continue
        intervals = [
            (rect.x_ft, rect.max_x)
            for rect in rects
            if rect.y_ft < y2 - EPS and rect.max_y > y1 + EPS
        ]
        merged = _merge_intervals(intervals)
        if len(merged) > 1:
            has_multi_span_y = True

    rectangularity_ratio = (union_area / bbox_area) if bbox_area > EPS else 1.0
    axis_convex = not (has_multi_span_x or has_multi_span_y)
    return union_area, rectangularity_ratio, axis_convex


def _build_soft_scoring_context(
    agent_input: Agent2Input, agent_output: Agent2Output
) -> SoftScoringContext:
    footprint_width = agent_input.selected_program.footprint_width_ft
    footprint_depth = agent_input.selected_program.footprint_depth_ft
    footprint_area = footprint_width * footprint_depth
    bedroom_count = agent_input.selected_program.bedrooms

    rooms = list(agent_output.rooms)
    bedrooms = [r for r in rooms if r.room_type == "bedroom"]
    bathrooms = [r for r in rooms if r.room_type == "bathroom"]
    kitchens = [r for r in rooms if r.room_type == "kitchen"]
    livings = [r for r in rooms if r.room_type == "living"]
    open_living_kitchens = [r for r in rooms if r.room_type == "open_living_kitchen"]
    plumbing_rooms = [r for r in rooms if r.room_type in {"bathroom", "circulation", "storage"}]

    exterior_walls = [w for w in agent_output.walls_intent if w.kind == "exterior"]
    interior_walls = [w for w in agent_output.walls_intent if w.kind == "interior"]
    doors = [o for o in agent_output.openings_intent if o.opening_type == "door"]
    room_groups_by_type: dict[str, list[RoomIntent]] = {}
    for room in rooms:
        room_groups_by_type.setdefault(room.room_type, []).append(room)

    total_room_area = sum(_room_area(room) for room in rooms)
    room_utilization = (total_room_area / footprint_area) if footprint_area > EPS else 0.0
    unassigned_pct = 1.0 - room_utilization
    aspect_ratio = (footprint_width / footprint_depth) if footprint_depth > EPS else 0.0

    recommended_open_plan = False
    if bedroom_count == 1:
        recommended_open_plan = True
    elif bedroom_count == 2 and aspect_ratio > 1.8:
        recommended_open_plan = True
    elif bedroom_count == 2 and footprint_area < 900:
        recommended_open_plan = True

    _room_union_area, room_rectangularity_ratio, room_axis_convex = _compute_layout_shape_metrics(
        rooms
    )

    return SoftScoringContext(
        agent_input=agent_input,
        agent_output=agent_output,
        footprint_width=footprint_width,
        footprint_depth=footprint_depth,
        footprint_area=footprint_area,
        bedroom_count=bedroom_count,
        rooms=rooms,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        kitchens=kitchens,
        livings=livings,
        open_living_kitchens=open_living_kitchens,
        plumbing_rooms=plumbing_rooms,
        exterior_walls=exterior_walls,
        interior_walls=interior_walls,
        doors=doors,
        room_groups_by_type=room_groups_by_type,
        total_room_area=total_room_area,
        room_utilization=room_utilization,
        unassigned_pct=unassigned_pct,
        aspect_ratio=aspect_ratio,
        recommended_open_plan=recommended_open_plan,
        room_rectangularity_ratio=room_rectangularity_ratio,
        room_axis_convex=room_axis_convex,
    )


def _rule_room_budget(ctx: SoftScoringContext, acc: SoftScoringAccumulator) -> None:
    max_room_area = ctx.footprint_area * 0.81
    if ctx.total_room_area > max_room_area + EPS:
        acc.add_deduction(
            "ROOM_AREA_OVER_81_PCT",
            15,
            "Total room area exceeds 81% footprint budget.",
        )
    if ctx.unassigned_pct < 0.14 or ctx.unassigned_pct > 0.21:
        acc.add_deduction(
            "WALL_CIRCULATION_BUDGET_OFF_TARGET",
            8,
            "Walls + circulation are outside the 14%-21% expected range.",
        )


def _rule_open_plan_partition(ctx: SoftScoringContext, acc: SoftScoringAccumulator) -> None:
    if ctx.recommended_open_plan and ctx.kitchens and ctx.livings:
        if _shared_boundary_partition_exists(ctx.livings, ctx.kitchens, ctx.interior_walls):
            acc.add_deduction(
                "OPEN_PLAN_RECOMMENDED_BUT_PARTITIONED",
                8,
                "Open plan is recommended, but a living-kitchen partition wall exists.",
            )


def _rule_convexity_rectangularity(
    ctx: SoftScoringContext, acc: SoftScoringAccumulator
) -> None:
    if not ctx.room_axis_convex:
        acc.add_deduction(
            "LAYOUT_CONVEXITY_GAP",
            10,
            "Room union has multi-span slices (shape is non-convex/disconnected).",
        )
    if ctx.room_rectangularity_ratio < 0.80 - EPS:
        acc.add_deduction(
            "LAYOUT_RECTANGULARITY_LOW",
            8,
            (
                "Room union fills under 80% of its occupied bounding box "
                f"(ratio={ctx.room_rectangularity_ratio:.3f})."
            ),
        )


def _rule_singleton_room_convexity(
    ctx: SoftScoringContext, acc: SoftScoringAccumulator
) -> None:
    required_counts = ctx.agent_input.layout_rules.required_room_counts
    singleton_room_types = {
        room_type
        for room_type, required_count in required_counts.items()
        if required_count == 1
    }
    for room_type in singleton_room_types:
        grouped_rooms = ctx.room_groups_by_type.get(room_type, [])
        if len(grouped_rooms) <= 1:
            continue
        _, rectangularity_ratio, axis_convex = _compute_layout_shape_metrics(grouped_rooms)
        if (not axis_convex) or rectangularity_ratio < 0.80 - EPS:
            acc.add_deduction(
                "ROOM_ZONE_RECTANGULARITY_LOW",
                15,
                (
                    f"Singleton room type '{room_type}' is split into {len(grouped_rooms)} "
                    f"pieces with low convexity/rectangularity (ratio={rectangularity_ratio:.3f})."
                ),
            )


def _rule_zone_order(ctx: SoftScoringContext, acc: SoftScoringAccumulator) -> None:
    axis = ctx.long_axis
    bed_center = _group_centroid_axis(ctx.bedrooms, axis=axis)
    plumbing_center = _group_centroid_axis(ctx.plumbing_rooms, axis=axis)
    living_center = _group_centroid_axis(ctx.living_zone_rooms, axis=axis)
    if (
        bed_center is not None
        and plumbing_center is not None
        and living_center is not None
    ):
        valid_order = (bed_center < plumbing_center < living_center) or (
            bed_center > plumbing_center > living_center
        )
        if not valid_order:
            acc.add_deduction(
                "ZONE_ORDER_INVALID",
                20,
                "Bedroom/plumbing/living zones are not in sequential order along the long axis.",
            )
            acc.add_deduction(
                "NO_ZONE_BUFFER",
                20,
                "Plumbing core is not acting as a buffer between bedroom and living zones.",
            )


def _rule_dimension_minimums(ctx: SoftScoringContext, acc: SoftScoringAccumulator) -> None:
    if ctx.bedroom_count == 1:
        for bed in ctx.bedrooms:
            if (
                bed.rect.width_ft < 10.0 - EPS
                or bed.rect.depth_ft < 11.0 - EPS
                or _room_area(bed) < 114.0 - EPS
            ):
                acc.add_deduction(
                    "BEDROOM_MIN_DIMENSION",
                    12,
                    f"Bedroom '{bed.room_id}' is below 1BR minimum dimensions.",
                )
    elif ctx.bedroom_count >= 2 and ctx.bedrooms:
        sorted_bedrooms = sorted(ctx.bedrooms, key=_room_area, reverse=True)
        primary = sorted_bedrooms[0]
        if (
            primary.rect.width_ft < 11.5 - EPS
            or primary.rect.depth_ft < 12.0 - EPS
            or _room_area(primary) < 131.0 - EPS
        ):
            acc.add_deduction(
                "PRIMARY_BEDROOM_MIN_DIMENSION",
                12,
                f"Primary bedroom '{primary.room_id}' is below 2BR minimum dimensions.",
            )
        for secondary in sorted_bedrooms[1:]:
            if (
                secondary.rect.width_ft < 11.0 - EPS
                or secondary.rect.depth_ft < 11.0 - EPS
                or _room_area(secondary) < 121.0 - EPS
            ):
                acc.add_deduction(
                    "SECONDARY_BEDROOM_MIN_DIMENSION",
                    10,
                    f"Secondary bedroom '{secondary.room_id}' is below minimum dimensions.",
                )

    for bath in ctx.bathrooms:
        if (
            bath.rect.width_ft < 5.0 - EPS
            or bath.rect.depth_ft < 7.0 - EPS
            or _room_area(bath) < 35.0 - EPS
        ):
            acc.add_deduction(
                "BATHROOM_MIN_DIMENSION",
                10,
                f"Bathroom '{bath.room_id}' is below minimum dimensions.",
            )

    if ctx.recommended_open_plan:
        combined_area = (
            sum(_room_area(r) for r in ctx.open_living_kitchens)
            if ctx.open_living_kitchens
            else sum(_room_area(r) for r in ctx.livings + ctx.kitchens)
        )
        if combined_area < 160.0 - EPS:
            acc.add_deduction(
                "OPEN_LIVING_KITCHEN_MIN_AREA",
                10,
                "Open living/kitchen area is below 160 sqft recommended minimum.",
            )
    else:
        for kitchen in ctx.kitchens:
            if (
                kitchen.rect.width_ft < 9.0 - EPS
                or kitchen.rect.depth_ft < 8.0 - EPS
                or _room_area(kitchen) < 72.0 - EPS
            ):
                acc.add_deduction(
                    "KITCHEN_MIN_DIMENSION",
                    8,
                    f"Kitchen '{kitchen.room_id}' is below standalone minimum dimensions.",
                )
        for living in ctx.livings:
            if (
                living.rect.width_ft < 9.5 - EPS
                or living.rect.depth_ft < 6.5 - EPS
                or _room_area(living) < 61.0 - EPS
            ):
                acc.add_deduction(
                    "LIVING_MIN_DIMENSION",
                    8,
                    f"Living room '{living.room_id}' is below standalone minimum dimensions.",
                )

    for corridor in [r for r in ctx.rooms if r.room_type == "circulation"]:
        if min(corridor.rect.width_ft, corridor.rect.depth_ft) < 3.5 - EPS:
            acc.add_deduction(
                "HALLWAY_TOO_NARROW",
                6,
                f"Circulation room '{corridor.room_id}' is under 3.5ft clear width.",
            )


def _add_pct_range_deduction(
    ctx: SoftScoringContext,
    acc: SoftScoringAccumulator,
    *,
    actual_area: float,
    min_pct: float,
    max_pct: float,
    code: str,
    penalty: int,
    description: str,
) -> None:
    if ctx.footprint_area <= EPS:
        return
    pct = actual_area / ctx.footprint_area
    if pct < min_pct - EPS or pct > max_pct + EPS:
        acc.add_deduction(code, penalty, description)


def _rule_area_share_ranges(ctx: SoftScoringContext, acc: SoftScoringAccumulator) -> None:
    if ctx.bedroom_count == 1 and ctx.bedrooms:
        _add_pct_range_deduction(
            ctx,
            acc,
            actual_area=sum(_room_area(b) for b in ctx.bedrooms),
            min_pct=0.22,
            max_pct=0.30,
            code="BEDROOM_AREA_SHARE_OUT_OF_RANGE",
            penalty=6,
            description="1BR bedroom area share is outside 22%-30%.",
        )
    elif ctx.bedroom_count >= 2 and ctx.bedrooms:
        sorted_beds = sorted(ctx.bedrooms, key=_room_area, reverse=True)
        _add_pct_range_deduction(
            ctx,
            acc,
            actual_area=_room_area(sorted_beds[0]),
            min_pct=0.13,
            max_pct=0.18,
            code="PRIMARY_BEDROOM_AREA_SHARE_OUT_OF_RANGE",
            penalty=6,
            description="Primary bedroom area share is outside 13%-18%.",
        )
        if len(sorted_beds) > 1:
            _add_pct_range_deduction(
                ctx,
                acc,
                actual_area=_room_area(sorted_beds[1]),
                min_pct=0.12,
                max_pct=0.16,
                code="SECONDARY_BEDROOM_AREA_SHARE_OUT_OF_RANGE",
                penalty=6,
                description="Secondary bedroom area share is outside 12%-16%.",
            )

    for bath in ctx.bathrooms:
        _add_pct_range_deduction(
            ctx,
            acc,
            actual_area=_room_area(bath),
            min_pct=0.04,
            max_pct=0.09,
            code="BATHROOM_AREA_SHARE_OUT_OF_RANGE",
            penalty=5,
            description=f"Bathroom '{bath.room_id}' area share is outside 4%-9%.",
        )

    if ctx.recommended_open_plan:
        _add_pct_range_deduction(
            ctx,
            acc,
            actual_area=(
                sum(_room_area(r) for r in ctx.open_living_kitchens)
                if ctx.open_living_kitchens
                else sum(_room_area(r) for r in ctx.livings + ctx.kitchens)
            ),
            min_pct=0.36 if ctx.bedroom_count == 1 else 0.32,
            max_pct=0.44 if ctx.bedroom_count == 1 else 0.40,
            code="OPEN_LIVING_KITCHEN_AREA_SHARE_OUT_OF_RANGE",
            penalty=6,
            description="Open living/kitchen share is outside target range.",
        )
    else:
        for kitchen in ctx.kitchens:
            _add_pct_range_deduction(
                ctx,
                acc,
                actual_area=_room_area(kitchen),
                min_pct=0.16,
                max_pct=0.22,
                code="KITCHEN_AREA_SHARE_OUT_OF_RANGE",
                penalty=5,
                description=f"Kitchen '{kitchen.room_id}' area share is outside 16%-22%.",
            )
        for living in ctx.livings:
            _add_pct_range_deduction(
                ctx,
                acc,
                actual_area=_room_area(living),
                min_pct=0.12,
                max_pct=0.18,
                code="LIVING_AREA_SHARE_OUT_OF_RANGE",
                penalty=5,
                description=f"Living '{living.room_id}' area share is outside 12%-18%.",
            )

    _add_pct_range_deduction(
        ctx,
        acc,
        actual_area=sum(_room_area(r) for r in ctx.plumbing_rooms),
        min_pct=0.12,
        max_pct=0.20,
        code="PLUMBING_CORE_AREA_SHARE_OUT_OF_RANGE",
        penalty=6,
        description="Plumbing core total area is outside 12%-20%.",
    )


def _rule_adjacency_and_access(ctx: SoftScoringContext, acc: SoftScoringAccumulator) -> None:
    if len(ctx.plumbing_rooms) > 1:
        visited: set[str] = set()
        stack = [ctx.plumbing_rooms[0].room_id]
        room_lookup = {room.room_id: room for room in ctx.plumbing_rooms}
        while stack:
            rid = stack.pop()
            if rid in visited:
                continue
            visited.add(rid)
            room = room_lookup[rid]
            for other in ctx.plumbing_rooms:
                if other.room_id in visited:
                    continue
                if _rects_connected(room.rect, other.rect):
                    stack.append(other.room_id)
        if len(visited) != len(ctx.plumbing_rooms):
            acc.add_deduction(
                "PLUMBING_CORE_FRAGMENTED",
                25,
                "Bathrooms/plumbing rooms are fragmented instead of clustered.",
            )

    for opening in ctx.doors:
        touched = ctx.opening_touches_room_types(opening)
        if "bathroom" in touched and "kitchen" in touched:
            acc.add_deduction(
                "BATH_DOOR_FACES_KITCHEN",
                25,
                f"Door '{opening.opening_id}' connects bathroom directly to kitchen.",
            )
            break

    exterior_wall_ids = {wall.wall_id for wall in ctx.exterior_walls}
    exterior_doors = [door for door in ctx.doors if door.wall_id in exterior_wall_ids]
    if not exterior_doors:
        acc.add_deduction(
            "ENTRY_DOOR_MISSING",
            20,
            "No exterior entry door was found.",
        )
    else:
        entry = exterior_doors[0]
        touched = ctx.opening_touches_room_types(entry)
        if "bedroom" in touched:
            acc.add_deduction(
                "ENTRY_INTO_BEDROOM",
                20,
                "Entry door opens directly into a bedroom zone.",
            )
        elif not ({"living", "kitchen"} & touched):
            acc.add_deduction(
                "ENTRY_INTO_HALLWAY_DEAD_END",
                20,
                "Entry door does not open into living zone.",
            )

        bed_center = _group_centroid_axis(ctx.bedrooms, axis=ctx.long_axis)
        living_center = _group_centroid_axis(ctx.living_zone_rooms, axis=ctx.long_axis)
        if bed_center is not None and living_center is not None:
            axis_value = (
                entry.anchor_local.x_ft
                if ctx.long_axis == "x"
                else entry.anchor_local.y_ft
            )
            expected_living_end = (
                ctx.footprint_width if ctx.long_axis == "x" else ctx.footprint_depth
            ) if living_center >= bed_center else 0.0
            if abs(axis_value - expected_living_end) > 1.0:
                acc.add_deduction(
                    "ENTRY_NOT_ON_LIVING_ZONE_END",
                    10,
                    "Entry door is not located on the living-zone end of the shell.",
                )

    for bedroom in ctx.bedrooms:
        edge_count = _room_exterior_edge_count(
            bedroom.rect, ctx.footprint_width, ctx.footprint_depth
        )
        if edge_count < 2:
            acc.add_deduction(
                "BEDROOM_NO_EXTERIOR_WALL",
                30,
                f"Bedroom '{bedroom.room_id}' has fewer than two exterior shell edges.",
            )
    if ctx.living_zone_rooms:
        living_has_exterior = any(
            _room_exterior_edge_count(room.rect, ctx.footprint_width, ctx.footprint_depth) >= 1
            for room in ctx.living_zone_rooms
        )
        if not living_has_exterior:
            acc.add_deduction(
                "LIVING_NO_EXTERIOR_WALL",
                15,
                "Living zone has no exterior wall access.",
            )

    if ctx.bedroom_count >= 2 and len(ctx.bedrooms) >= 2:
        sorted_beds = sorted(ctx.bedrooms, key=_room_area, reverse=True)
        primary = sorted_beds[0]
        primary_has_bath_access = False
        for opening in ctx.doors:
            touched = ctx.opening_touches_room_types(opening)
            if "bathroom" not in touched:
                continue
            if _point_on_room_boundary(primary.rect, opening.anchor_local):
                primary_has_bath_access = True
                break
        if not primary_has_bath_access:
            acc.add_deduction(
                "PRIMARY_BEDROOM_NO_BATH_ACCESS",
                15,
                "Primary bedroom lacks direct bathroom door access.",
            )

        bathrooms_with_guest_access = 0
        for bath in ctx.bathrooms:
            has_guest_access = any(
                _point_on_room_boundary(bath.rect, opening.anchor_local)
                and bool(
                    {"living", "kitchen", "circulation"}
                    & ctx.opening_touches_room_types(opening)
                )
                for opening in ctx.doors
            )
            if has_guest_access:
                bathrooms_with_guest_access += 1
        if ctx.bathrooms and bathrooms_with_guest_access == 0:
            acc.add_deduction(
                "SECOND_BATH_NOT_GUEST_ACCESSIBLE",
                15,
                "No bathroom is directly accessible from common/guest space.",
            )

        midpoint = (
            (ctx.footprint_width / 2.0)
            if ctx.long_axis == "x"
            else (ctx.footprint_depth / 2.0)
        )
        bed_positions = [
            (bed.rect.x_ft + bed.rect.width_ft / 2.0)
            if ctx.long_axis == "x"
            else (bed.rect.y_ft + bed.rect.depth_ft / 2.0)
            for bed in ctx.bedrooms
        ]
        if not (
            all(pos <= midpoint + EPS for pos in bed_positions)
            or all(pos >= midpoint - EPS for pos in bed_positions)
        ):
            acc.add_deduction(
                "BEDROOMS_NOT_CLUSTERED",
                20,
                "Bedrooms are split across opposite ends instead of clustered.",
            )

    if ctx.kitchens:
        kitchen_has_exterior = any(
            _room_exterior_edge_count(k.rect, ctx.footprint_width, ctx.footprint_depth) >= 1
            for k in ctx.kitchens
        )
        if not kitchen_has_exterior:
            acc.add_deduction(
                "KITCHEN_NO_EXTERIOR_WALL",
                10,
                "Kitchen lacks exterior wall adjacency (preferred for ventilation).",
            )


SOFT_SCORING_RULE_REGISTRY: tuple[SoftScoringRule, ...] = (
    SoftScoringRule(
        code="ROOM_BUDGET",
        description="Room utilization and wall/circulation budget targets.",
        apply=_rule_room_budget,
    ),
    SoftScoringRule(
        code="OPEN_PLAN_PARTITION",
        description="Open-plan recommendation should avoid partitioning.",
        apply=_rule_open_plan_partition,
    ),
    SoftScoringRule(
        code="CONVEXITY_RECTANGULARITY",
        description="Prefer convex, compact room unions over fragmented shapes.",
        apply=_rule_convexity_rectangularity,
    ),
    SoftScoringRule(
        code="SINGLETON_ROOM_CONVEXITY",
        description="Singleton room zones should not split into jagged wrap-around pieces.",
        apply=_rule_singleton_room_convexity,
    ),
    SoftScoringRule(
        code="ZONE_ORDER",
        description="Bedroom/plumbing/living sequencing should follow long-axis zoning.",
        apply=_rule_zone_order,
    ),
    SoftScoringRule(
        code="DIMENSION_MINIMUMS",
        description="Rooms should meet soft minimum dimensional guidance.",
        apply=_rule_dimension_minimums,
    ),
    SoftScoringRule(
        code="AREA_SHARE",
        description="Area shares should fall within target ranges by room/program type.",
        apply=_rule_area_share_ranges,
    ),
    SoftScoringRule(
        code="ADJACENCY_ACCESS",
        description="Plumbing clustering, entry placement, and access/circulation quality.",
        apply=_rule_adjacency_and_access,
    ),
)


def _run_soft_scoring_registry(
    ctx: SoftScoringContext, acc: SoftScoringAccumulator
) -> None:
    for rule in SOFT_SCORING_RULE_REGISTRY:
        rule.apply(ctx, acc)


def score_agent_2_soft_rules(agent_input: Agent2Input, agent_output: Agent2Output) -> dict[str, Any]:
    """Compute non-blocking quality telemetry for an Agent 2 layout."""
    if agent_output.conflict_flag:
        return {
            "score": 0,
            "status": "not_scored",
            "total_penalty": 0,
            "deductions": [],
            "metadata": {"reason": "agent_2_conflict"},
        }
    ctx = _build_soft_scoring_context(agent_input, agent_output)
    accumulator = SoftScoringAccumulator()
    _run_soft_scoring_registry(ctx, accumulator)

    total_penalty = sum(int(item["penalty"]) for item in accumulator.deductions)
    score = max(0, 100 - total_penalty)
    if score >= 80:
        status = "PASS"
    elif score >= 50:
        status = "SOFT_FAIL"
    else:
        status = "HARD_FAIL"

    return {
        "score": score,
        "status": status,
        "total_penalty": total_penalty,
        "deductions": accumulator.deductions,
        "metadata": {
            "footprint_area_sf": round(ctx.footprint_area, 4),
            "total_room_area_sf": round(ctx.total_room_area, 4),
            "room_utilization_pct": round(ctx.room_utilization, 4),
            "unassigned_pct": round(ctx.unassigned_pct, 4),
            "aspect_ratio": round(ctx.aspect_ratio, 4),
            "recommended_open_plan": ctx.recommended_open_plan,
            "bedroom_count": ctx.bedroom_count,
            "layout_rectangularity_ratio": round(ctx.room_rectangularity_ratio, 4),
            "layout_axis_convex": ctx.room_axis_convex,
            "sections_6_7_dropped": True,
        },
    }


def score_agent_2_layout(agent_input: Agent2Input, agent_output: Agent2Output) -> dict[str, Any]:
    """Compatibility wrapper for eval harness imports."""
    return score_agent_2_soft_rules(agent_input, agent_output)


def score_agent2_layout(agent_input: Agent2Input, agent_output: Agent2Output) -> dict[str, Any]:
    """Compatibility wrapper for tests and ad-hoc scripts."""
    return score_agent_2_soft_rules(agent_input, agent_output)

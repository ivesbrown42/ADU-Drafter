"""Canonical runtime contracts for Agent 1/Agent 2/Python handoffs."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

StreetFrontage = Literal["north", "south", "east", "west"]
OriginCorner = Literal["SW", "SE", "NW", "NE"]
PlacementStrategy = Literal["rear-left", "rear-right", "rear-center", "conflict"]
CandidateStrategy = Literal["rear-left", "rear-right", "rear-center"]
LongAxis = Literal["x", "y"]
WallRole = Literal["front", "rear", "left", "right"]
TraceStatus = Literal["accepted", "rejected"]
RoomType = Literal[
    "bedroom",
    "bathroom",
    "kitchen",
    "living",
    "open_living_kitchen",
    "circulation",
    "storage",
]
WallKind = Literal["exterior", "interior"]
OpeningType = Literal["door", "window"]


class RatioPoint(BaseModel):
    """Normalized point in a local 2D frame, bounded to [0, 1]."""

    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)


class SiteMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lot_id: str = Field(min_length=1)
    rectangular_lot: bool
    lot_width_ft: float = Field(gt=0)
    lot_depth_ft: float = Field(gt=0)
    street_frontage: StreetFrontage
    origin_corner: OriginCorner

    @model_validator(mode="after")
    def require_rectangular_lot(self) -> "SiteMetadata":
        if not self.rectangular_lot:
            raise ValueError("PoC supports rectangular lots only")
        return self


class ExistingStructure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    is_primary_dwelling: bool = False
    offset_from_origin_x_ft: float
    offset_from_origin_y_ft: float
    width_ft: float = Field(gt=0)
    depth_ft: float = Field(gt=0)


class PrimaryDwellingWall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_label: str = Field(min_length=1)
    wall_role: WallRole


class ZoneCheckResults(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_1_rear_setback: bool
    check_2_side_setback: bool
    check_3_front_constraint: bool
    check_4_primary_separation: bool
    check_5_other_structure_separation: bool


class CandidateZoneMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rear_setback_ft: float = Field(ge=0)
    side_setback_ft: float = Field(ge=0)
    clearance_to_primary_ft: float = Field(ge=0)


class CandidateZone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(min_length=1)
    strategy: CandidateStrategy
    zone_polygon_sw_origin: list[tuple[float, float]] = Field(min_length=4)
    check_results: ZoneCheckResults
    metrics: CandidateZoneMetrics
    failed_reason_codes: list[str] = Field(default_factory=list)


class ProgramCatalogEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: str = Field(min_length=1)
    bedrooms: int = Field(ge=0)
    bathrooms: int = Field(ge=0)
    target_area_sf: float = Field(gt=0)
    footprint_width_ft: float = Field(gt=0)
    footprint_depth_ft: float = Field(gt=0)


class ClientRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_size_sf: float = Field(gt=0)
    bedrooms_preference: int = Field(ge=0)
    bathrooms_preference: int = Field(ge=0)
    transit_proximity: bool


class Agent1Input(BaseModel):
    """Input contract for Agent 1 site-decision step."""

    model_config = ConfigDict(extra="forbid")

    site_metadata: SiteMetadata
    existing_structures: list[ExistingStructure] = Field(min_length=1)
    primary_dwelling_walls: list[PrimaryDwellingWall] = Field(min_length=1)
    candidate_zones: list[CandidateZone] = Field(min_length=1)
    program_catalog: list[ProgramCatalogEntry] = Field(min_length=1)
    client_request: ClientRequest

    @model_validator(mode="after")
    def validate_primary_structure(self) -> "Agent1Input":
        primary_count = sum(1 for structure in self.existing_structures if structure.is_primary_dwelling)
        if primary_count != 1:
            raise ValueError("Exactly one existing structure must be marked as primary dwelling")
        rear_walls = [wall for wall in self.primary_dwelling_walls if wall.wall_role == "rear"]
        if not rear_walls:
            raise ValueError("primary_dwelling_walls must include a wall with wall_role='rear'")
        return self


class Agent1DecisionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_strategy: PlacementStrategy
    selected_zone_id: str | None
    selected_program_id: str | None
    primary_dwelling_rear_wall_label: str | None


class ComplianceTraceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(min_length=1)
    strategy: CandidateStrategy
    check_results: ZoneCheckResults
    status: TraceStatus
    reason_codes: list[str] = Field(default_factory=list)


class Agent1ForAgent2(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: str | None
    program_id: str | None
    strategy: PlacementStrategy
    constraints_profile_id: str = Field(min_length=1)


class StructureSeparation(BaseModel):
    """Per-structure separation result emitted by Agent 1 when available."""

    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    clearance_ft: float = Field(ge=0)
    minimum_required_ft: float = Field(default=6, ge=0)
    compliant: bool


class Agent1Output(BaseModel):
    """Output contract emitted by Agent 1 site-decision step."""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1)
    version: str = Field(min_length=1)
    conflict_flag: bool
    conflict_reasons: list[str] = Field(default_factory=list)
    decision_summary: Agent1DecisionSummary
    compliance_trace: list[ComplianceTraceEntry] = Field(default_factory=list)
    for_agent_2: Agent1ForAgent2
    structure_separations: list[StructureSeparation] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_conflict_shape(self) -> "Agent1Output":
        strategy = self.decision_summary.selected_strategy
        if self.conflict_flag:
            if strategy != "conflict":
                raise ValueError("conflict_flag=true requires selected_strategy='conflict'")
            if self.decision_summary.selected_zone_id is not None:
                raise ValueError("conflict mode requires selected_zone_id=null")
            if self.decision_summary.selected_program_id is not None:
                raise ValueError("conflict mode requires selected_program_id=null")
        else:
            if strategy == "conflict":
                raise ValueError("selected_strategy='conflict' requires conflict_flag=true")
            if self.decision_summary.selected_zone_id is None:
                raise ValueError("non-conflict output requires selected_zone_id")
            if self.decision_summary.selected_program_id is None:
                raise ValueError("non-conflict output requires selected_program_id")
        return self


class SiteContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lot_width_ft: float = Field(gt=0)
    lot_depth_ft: float = Field(gt=0)
    street_frontage: StreetFrontage
    input_coordinates_normalized_to_sw: bool

    @model_validator(mode="after")
    def require_normalized(self) -> "SiteContext":
        if not self.input_coordinates_normalized_to_sw:
            raise ValueError("input_coordinates_normalized_to_sw must be true")
        return self


class SelectedZone(BaseModel):
    model_config = ConfigDict(extra="forbid")

    zone_id: str = Field(min_length=1)
    zone_polygon_sw_origin: list[tuple[float, float]] = Field(min_length=4)


class SelectedProgram(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: str = Field(min_length=1)
    bedrooms: int = Field(ge=0)
    bathrooms: int = Field(ge=0)
    target_area_sf: float = Field(gt=0)
    footprint_width_ft: float = Field(gt=0)
    footprint_depth_ft: float = Field(gt=0)


class MinimumRoomDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_width_ft: float = Field(gt=0)
    min_depth_ft: float = Field(gt=0)
    min_area_sf: float | None = Field(default=None, gt=0)


class LayoutRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open_plan_required: bool = False
    plumbing_core_required: bool = True
    long_axis: LongAxis = "x"
    required_room_counts: dict[RoomType, int] = Field(default_factory=dict)
    minimum_room_dimensions: dict[RoomType, MinimumRoomDimension] = Field(default_factory=dict)


class DesignRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grid_step_ft: float = Field(gt=0)
    wall_thickness_options_ft: list[float] = Field(min_length=1)
    max_retry_iteration: int = Field(ge=1)


class Agent2Input(BaseModel):
    """Input contract for Agent 2 design step."""

    model_config = ConfigDict(extra="forbid")

    agent_1_output: Agent1Output
    site_context: SiteContext
    selected_zone: SelectedZone
    selected_program: SelectedProgram
    design_rules: DesignRules
    layout_rules: LayoutRules = Field(default_factory=LayoutRules)

    @model_validator(mode="after")
    def validate_selection_alignment(self) -> "Agent2Input":
        if self.agent_1_output.conflict_flag:
            raise ValueError("Cannot construct Agent2Input when Agent1 output is in conflict mode")
        d = self.agent_1_output.decision_summary
        if d.selected_zone_id != self.selected_zone.zone_id:
            raise ValueError("selected_zone.zone_id must match Agent1 selected_zone_id")
        if d.selected_program_id != self.selected_program.program_id:
            raise ValueError("selected_program.program_id must match Agent1 selected_program_id")
        return self


class DesignSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    program_id: str = Field(min_length=1)
    zone_id: str = Field(min_length=1)
    layout_type: str = Field(min_length=1)


class RoomIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    room_id: str = Field(min_length=1)
    room_type: RoomType
    label: str = Field(min_length=1)
    center_local: "LocalPoint"
    target_area_sf: float = Field(gt=0)
    rect: "LocalRect"
    adjacency: list[str] = Field(default_factory=list)


class LocalPoint(BaseModel):
    """A 2D point in zone-local feet coordinates."""

    model_config = ConfigDict(extra="forbid")

    x_ft: float = Field(ge=0)
    y_ft: float = Field(ge=0)


class LocalRect(BaseModel):
    """Axis-aligned room rectangle in zone-local feet coordinates."""

    model_config = ConfigDict(extra="forbid")

    x_ft: float = Field(ge=0)
    y_ft: float = Field(ge=0)
    width_ft: float = Field(gt=0)
    depth_ft: float = Field(gt=0)

    @property
    def max_x(self) -> float:
        return self.x_ft + self.width_ft

    @property
    def max_y(self) -> float:
        return self.y_ft + self.depth_ft


class WallIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_id: str = Field(min_length=1)
    kind: WallKind
    start_local: LocalPoint
    end_local: LocalPoint
    thickness_ft: float = Field(gt=0)


class OpeningIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening_id: str = Field(min_length=1)
    wall_id: str = Field(min_length=1)
    opening_type: OpeningType
    anchor_local: LocalPoint
    width_ft: float = Field(gt=0)


class Agent2Output(BaseModel):
    """Output contract emitted by Agent 2 design-intent step."""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1)
    version: str = Field(min_length=1)
    conflict_flag: bool
    design_summary: DesignSummary
    rooms: list[RoomIntent] = Field(default_factory=list)
    walls_intent: list[WallIntent] = Field(default_factory=list)
    openings_intent: list[OpeningIntent] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_conflict_payload(self) -> "Agent2Output":
        if self.conflict_flag and (self.rooms or self.walls_intent or self.openings_intent):
            raise ValueError("Agent2 conflict output must not include rooms/walls/openings")
        return self


class GeometryResolverInput(BaseModel):
    """Input contract for deterministic geometry resolver service."""

    model_config = ConfigDict(extra="forbid")

    agent_1_output: Agent1Output
    agent_2_output: Agent2Output
    site_context: SiteContext
    selected_zone: SelectedZone | None = None
    selected_program: SelectedProgram | None = None
    design_rules: DesignRules
    existing_structures_passthrough: list[ExistingStructure] = Field(default_factory=list)
    input_coordinates_normalized_to_sw: bool

    @model_validator(mode="after")
    def validate_normalized_flag(self) -> "GeometryResolverInput":
        if not self.input_coordinates_normalized_to_sw:
            raise ValueError("geometry resolver requires input_coordinates_normalized_to_sw=true")
        if not self.agent_1_output.conflict_flag:
            if self.selected_zone is None:
                raise ValueError("non-conflict resolver payload requires selected_zone")
            if self.selected_program is None:
                raise ValueError("non-conflict resolver payload requires selected_program")
            if self.agent_2_output.design_summary.zone_id != self.selected_zone.zone_id:
                raise ValueError("agent_2_output zone_id must match selected_zone.zone_id")
            if self.agent_2_output.design_summary.program_id != self.selected_program.program_id:
                raise ValueError("agent_2_output program_id must match selected_program.program_id")
        return self


class PolylineBoundary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    linetype: str = Field(min_length=1)
    color: int
    points: list[tuple[float, float]] = Field(min_length=5)


class ExistingStructureDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    layer: str = Field(min_length=1)
    linetype: str = Field(min_length=1)
    color: int
    sw_corner: tuple[float, float]
    ne_corner: tuple[float, float]
    points: list[tuple[float, float]] = Field(min_length=5)
    label_anchor: tuple[float, float]
    label_text: str = Field(min_length=1)
    label_height: float = Field(gt=0)


class LabelLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    color: int
    anchor: tuple[float, float]
    text: str = Field(min_length=1)
    height: float = Field(gt=0)
    alignment: Literal["MIDDLE_CENTER"]


class ADUFootprintDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    linetype: str = Field(min_length=1)
    color: int
    sw_corner: tuple[float, float]
    ne_corner: tuple[float, float]
    points: list[tuple[float, float]] = Field(min_length=5)
    side_placement: Literal["left", "right", "centered"]


class SeparationZoneDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    linetype: str = Field(min_length=1)
    color: int
    sw_corner: tuple[float, float]
    ne_corner: tuple[float, float]
    points: list[tuple[float, float]] = Field(min_length=5)


class WallAbsoluteDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_id: str = Field(min_length=1)
    kind: WallKind
    start: tuple[float, float]
    end: tuple[float, float]
    thickness_ft: float = Field(gt=0)
    layer: str = Field(min_length=1)


class OpeningAbsoluteDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening_id: str = Field(min_length=1)
    opening_type: OpeningType
    wall_id: str = Field(min_length=1)
    anchor: tuple[float, float]
    width_ft: float = Field(gt=0)


class ADUElementsDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    footprint: ADUFootprintDrawing
    separation_zone: SeparationZoneDrawing
    label_lines: list[LabelLine]
    room_labels: list[LabelLine] = Field(default_factory=list)
    walls_absolute: list[WallAbsoluteDrawing] = Field(default_factory=list)
    openings_absolute: list[OpeningAbsoluteDrawing] = Field(default_factory=list)


class ConflictNoticeLine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    anchor: tuple[float, float]
    text: str = Field(min_length=1)
    height: float = Field(gt=0)


class ConflictNotice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    line1: ConflictNoticeLine
    line2: ConflictNoticeLine


class DimensionEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Literal["LOT_WIDTH", "LOT_DEPTH", "ADU_WIDTH", "ADU_DEPTH"]
    layer: str = Field(min_length=1)
    color: int
    p1: tuple[float, float]
    p2: tuple[float, float]
    dimline_position: tuple[float, float]
    text: str = Field(min_length=1)


class StreetLabelDrawing(BaseModel):
    model_config = ConfigDict(extra="forbid")

    layer: str = Field(min_length=1)
    color: int
    anchor: tuple[float, float]
    text: str = Field(min_length=1)
    height: float = Field(gt=0)
    alignment: Literal["MIDDLE_CENTER"]


class SeparationComplianceMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str = Field(min_length=1)
    layer: str = Field(min_length=1)
    compliant: bool
    circle_center: tuple[float, float]
    circle_radius: float = Field(gt=0)
    circle_color: int
    text_anchor: tuple[float, float]
    text: str = Field(min_length=1)
    text_height: float = Field(gt=0)


class DrawingInstructionPayload(BaseModel):
    """Deterministic drawing instruction payload emitted by geometry resolver."""

    model_config = ConfigDict(extra="forbid")

    agent: str = Field(min_length=1)
    version: str = Field(min_length=1)
    coordinate_system: Literal["SW-origin-feet"]
    units: Literal["feet"]
    conflict_flag: bool
    lot_boundary: PolylineBoundary
    setback_boundary: PolylineBoundary
    existing_structures: list[ExistingStructureDrawing] = Field(default_factory=list)
    adu_elements: ADUElementsDrawing | None
    conflict_notice: ConflictNotice | None
    dimensions: list[DimensionEntry] = Field(default_factory=list)
    street_label: StreetLabelDrawing
    separation_compliance_markers: list[SeparationComplianceMarker] = Field(default_factory=list)
    geometry_flags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_conflict_dimensions(self) -> "DrawingInstructionPayload":
        ids = {dimension.id for dimension in self.dimensions}
        if "LOT_WIDTH" not in ids or "LOT_DEPTH" not in ids:
            raise ValueError("dimensions must include LOT_WIDTH and LOT_DEPTH")
        if self.conflict_flag:
            if self.adu_elements is not None:
                raise ValueError("conflict payload must set adu_elements to null")
            if self.conflict_notice is None:
                raise ValueError("conflict payload requires conflict_notice")
            if "ADU_WIDTH" in ids or "ADU_DEPTH" in ids:
                raise ValueError("conflict payload must omit ADU_WIDTH/ADU_DEPTH dimensions")
        return self


def _load_json(path: Path | str) -> dict:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def load_agent_1_input(path: Path | str) -> Agent1Input:
    return Agent1Input.model_validate(_load_json(path))


def load_agent_1_output(path: Path | str) -> Agent1Output:
    return Agent1Output.model_validate(_load_json(path))


def load_agent_2_input(path: Path | str) -> Agent2Input:
    return Agent2Input.model_validate(_load_json(path))


def load_agent_2_output(path: Path | str) -> Agent2Output:
    return Agent2Output.model_validate(_load_json(path))


def load_geometry_resolver_input(path: Path | str) -> GeometryResolverInput:
    return GeometryResolverInput.model_validate(_load_json(path))


def load_drawing_instruction_payload(path: Path | str) -> DrawingInstructionPayload:
    return DrawingInstructionPayload.model_validate(_load_json(path))


def _existing_ids(items: Sequence[str]) -> set[str]:
    return set(items)


def ensure_sw_normalized(input_coordinates_normalized_to_sw: bool) -> None:
    """Fail deterministically unless coordinates are SW normalized."""
    if not input_coordinates_normalized_to_sw:
        raise ValueError("input_coordinates_normalized_to_sw must be true")


def validate_agent_1_output_against_input(agent_input: Agent1Input, agent_output: Agent1Output) -> None:
    """Cross-validate Agent 1 output IDs and strategy against Agent 1 input."""

    zone_ids = _existing_ids(zone.zone_id for zone in agent_input.candidate_zones)
    program_ids = _existing_ids(program.program_id for program in agent_input.program_catalog)
    rear_wall_labels = _existing_ids(
        wall.wall_label for wall in agent_input.primary_dwelling_walls if wall.wall_role == "rear"
    )

    d = agent_output.decision_summary
    f = agent_output.for_agent_2

    if d.selected_strategy != f.strategy:
        raise ValueError("Agent1 output mismatch: decision_summary.selected_strategy != for_agent_2.strategy")
    if d.selected_zone_id != f.zone_id:
        raise ValueError("Agent1 output mismatch: decision_summary.selected_zone_id != for_agent_2.zone_id")
    if d.selected_program_id != f.program_id:
        raise ValueError("Agent1 output mismatch: decision_summary.selected_program_id != for_agent_2.program_id")

    if not agent_output.conflict_flag:
        if d.selected_zone_id not in zone_ids:
            raise ValueError(f"selected_zone_id '{d.selected_zone_id}' not found in candidate_zones")
        if d.selected_program_id not in program_ids:
            raise ValueError(f"selected_program_id '{d.selected_program_id}' not found in program_catalog")
        if d.primary_dwelling_rear_wall_label not in rear_wall_labels:
            raise ValueError(
                f"primary_dwelling_rear_wall_label '{d.primary_dwelling_rear_wall_label}' "
                "not found in primary_dwelling_walls with wall_role='rear'"
            )


def build_agent_2_input(
    agent_input: Agent1Input,
    agent_output: Agent1Output,
    *,
    input_coordinates_normalized_to_sw: bool = True,
    grid_step_ft: float = 0.5,
    wall_thickness_options_ft: list[float] | None = None,
    max_retry_iteration: int = 3,
) -> Agent2Input:
    """Build deterministic Agent 2 input payload from validated Agent 1 artifacts."""

    validate_agent_1_output_against_input(agent_input, agent_output)

    if agent_output.conflict_flag:
        raise ValueError("Cannot build Agent2Input from conflict Agent1 output")

    wall_thickness_options_ft = wall_thickness_options_ft or [0.35, 0.5]
    selected_zone_id = agent_output.decision_summary.selected_zone_id
    selected_program_id = agent_output.decision_summary.selected_program_id

    zone = next(zone for zone in agent_input.candidate_zones if zone.zone_id == selected_zone_id)
    program = next(program for program in agent_input.program_catalog if program.program_id == selected_program_id)
    layout_rules = _build_layout_rules(program)

    payload = {
        "agent_1_output": agent_output.model_dump(mode="json"),
        "site_context": {
            "lot_width_ft": agent_input.site_metadata.lot_width_ft,
            "lot_depth_ft": agent_input.site_metadata.lot_depth_ft,
            "street_frontage": agent_input.site_metadata.street_frontage,
            "input_coordinates_normalized_to_sw": input_coordinates_normalized_to_sw,
        },
        "selected_zone": {
            "zone_id": zone.zone_id,
            "zone_polygon_sw_origin": zone.zone_polygon_sw_origin,
        },
        "selected_program": program.model_dump(mode="json"),
        "design_rules": {
            "grid_step_ft": grid_step_ft,
            "wall_thickness_options_ft": wall_thickness_options_ft,
            "max_retry_iteration": max_retry_iteration,
        },
        "layout_rules": layout_rules.model_dump(mode="json"),
    }
    return Agent2Input.model_validate(payload)


def _build_layout_rules(program: ProgramCatalogEntry) -> LayoutRules:
    open_plan_required = program.bedrooms == 1
    long_axis: LongAxis = "x" if program.footprint_width_ft >= program.footprint_depth_ft else "y"
    if open_plan_required:
        required_room_counts: dict[RoomType, int] = {
            "bedroom": program.bedrooms,
            "bathroom": program.bathrooms,
            "open_living_kitchen": 1,
        }
        minimum_room_dimensions: dict[RoomType, MinimumRoomDimension] = {
            "bedroom": MinimumRoomDimension(
                min_width_ft=10.0,
                min_depth_ft=11.0,
                min_area_sf=114.0,
            ),
            "bathroom": MinimumRoomDimension(
                min_width_ft=5.0,
                min_depth_ft=7.5,
                min_area_sf=37.0,
            ),
            "open_living_kitchen": MinimumRoomDimension(
                min_width_ft=16.0,
                min_depth_ft=10.0,
                min_area_sf=160.0,
            ),
        }
    else:
        required_room_counts = {
            "bedroom": program.bedrooms,
            "bathroom": program.bathrooms,
            "kitchen": 1,
            "living": 1,
        }
        minimum_room_dimensions = {
            "bedroom": MinimumRoomDimension(
                min_width_ft=10.0,
                min_depth_ft=11.0,
                min_area_sf=114.0,
            ),
            "bathroom": MinimumRoomDimension(
                min_width_ft=5.0,
                min_depth_ft=7.5,
                min_area_sf=37.0,
            ),
            "kitchen": MinimumRoomDimension(
                min_width_ft=9.0,
                min_depth_ft=8.0,
                min_area_sf=72.0,
            ),
            "living": MinimumRoomDimension(
                min_width_ft=9.5,
                min_depth_ft=6.5,
                min_area_sf=61.0,
            ),
        }
    return LayoutRules(
        open_plan_required=open_plan_required,
        plumbing_core_required=True,
        long_axis=long_axis,
        required_room_counts=required_room_counts,
        minimum_room_dimensions=minimum_room_dimensions,
    )


def validate_agent_2_output_against_input(agent_input: Agent2Input, agent_output: Agent2Output) -> None:
    """Cross-validate Agent 2 output IDs against Agent 2 input contract."""

    if agent_output.conflict_flag:
        return
    if agent_output.design_summary.zone_id != agent_input.selected_zone.zone_id:
        raise ValueError("Agent2 output zone_id does not match Agent2 input selected_zone")
    if agent_output.design_summary.program_id != agent_input.selected_program.program_id:
        raise ValueError("Agent2 output program_id does not match Agent2 input selected_program")

    zone_xs = [pt[0] for pt in agent_input.selected_zone.zone_polygon_sw_origin]
    zone_ys = [pt[1] for pt in agent_input.selected_zone.zone_polygon_sw_origin]
    zone_width_ft = max(zone_xs) - min(zone_xs)
    zone_depth_ft = max(zone_ys) - min(zone_ys)
    footprint_width_ft = agent_input.selected_program.footprint_width_ft
    footprint_depth_ft = agent_input.selected_program.footprint_depth_ft
    grid = agent_input.design_rules.grid_step_ft
    if zone_width_ft <= 0 or zone_depth_ft <= 0:
        raise ValueError("selected_zone has non-positive width/depth")
    if footprint_width_ft > zone_width_ft + 1e-6 or footprint_depth_ft > zone_depth_ft + 1e-6:
        raise ValueError(
            "PROGRAM_EXCEEDS_ZONE: selected_program footprint exceeds selected_zone bounds"
        )

    def _is_snapped(value: float) -> bool:
        quotient = value / grid
        return abs(quotient - round(quotient)) <= 1e-6

    def _validate_local_point(name: str, x: float, y: float) -> None:
        if x < 0 or y < 0 or x > footprint_width_ft or y > footprint_depth_ft:
            raise ValueError(f"{name} is outside zone-local bounds")
        if not _is_snapped(x) or not _is_snapped(y):
            raise ValueError(f"{name} is not snapped to grid_step_ft={grid}")
    
    layout_rules = agent_input.layout_rules
    open_plan_required = layout_rules.open_plan_required or agent_input.selected_program.bedrooms == 1
    if layout_rules.required_room_counts:
        required_room_counts = dict(layout_rules.required_room_counts)
    elif open_plan_required:
        required_room_counts: dict[RoomType, int] = {
            "bedroom": agent_input.selected_program.bedrooms,
            "bathroom": agent_input.selected_program.bathrooms,
            "open_living_kitchen": 1,
        }
    else:
        required_room_counts = {
            "bedroom": agent_input.selected_program.bedrooms,
            "bathroom": agent_input.selected_program.bathrooms,
            "kitchen": 1,
            "living": 1,
        }
    room_type_counts: dict[RoomType, int] = {
        room_type: 0 for room_type in required_room_counts
    }

    room_ids: set[str] = set()
    room_rects: list[tuple[str, float, float, float, float]] = []
    room_groups: dict[RoomType, list[RoomIntent]] = {}
    total_room_area = 0.0
    for room in agent_output.rooms:
        if room.room_id in room_ids:
            raise ValueError(f"Duplicate room_id '{room.room_id}' in Agent2 output")
        room_ids.add(room.room_id)
        if room.room_type in room_type_counts:
            room_type_counts[room.room_type] += 1
        room_groups.setdefault(room.room_type, []).append(room)
        rect = room.rect
        if (
            rect.x_ft < 0
            or rect.y_ft < 0
            or rect.max_x > footprint_width_ft
            or rect.max_y > footprint_depth_ft
        ):
            raise ValueError(f"Room '{room.room_id}' extends outside selected zone bounds")
        total_room_area += rect.width_ft * rect.depth_ft
        room_rects.append((room.room_id, rect.x_ft, rect.y_ft, rect.max_x, rect.max_y))

    if open_plan_required and (
        room_groups.get("living") or room_groups.get("kitchen")
    ):
        raise ValueError(
            "Error: OPEN_PLAN_REQUIRED. open_plan_required=true in layout_rules requires "
            "a single 'open_living_kitchen' room and forbids separate living/kitchen rooms. "
            "Merge living and kitchen into one open_living_kitchen room."
        )

    for room_type, required_count in required_room_counts.items():
        if required_count <= 0:
            continue
        actual_count = room_type_counts.get(room_type, 0)
        if actual_count < required_count:
            type_code = room_type.upper()
            raise ValueError(
                f"Error: MISSING_{type_code}. layout_rules.required_room_counts requires >= "
                f"{required_count} {room_type} room(s), got {actual_count}."
            )

    # Room rectangles may touch at boundaries but must not overlap with positive area.
    for i in range(len(room_rects)):
        id_i, ax1, ay1, ax2, ay2 = room_rects[i]
        for j in range(i + 1, len(room_rects)):
            id_j, bx1, by1, bx2, by2 = room_rects[j]
            overlap_w = min(ax2, bx2) - max(ax1, bx1)
            overlap_h = min(ay2, by2) - max(ay1, by1)
            if overlap_w > 0 and overlap_h > 0:
                raise ValueError(f"Rooms '{id_i}' and '{id_j}' overlap")

    zone_area = zone_width_ft * zone_depth_ft
    if total_room_area > zone_area + 1e-6:
        raise ValueError("Total room area exceeds selected zone area")

    def _validate_room_minimums(
        room: RoomIntent,
        *,
        room_type: RoomType,
        min_width_ft: float,
        min_depth_ft: float,
        min_area_sf: float | None,
    ) -> None:
        if room.rect.width_ft < min_width_ft - 1e-6:
            raise ValueError(
                "Error: PROPORTION_VIOLATION. "
                f"layout_rules.minimum_room_dimensions.{room_type}.min_width_ft={min_width_ft:.1f} "
                f"but room_id='{room.room_id}' width is {room.rect.width_ft:.2f}ft. "
                "Increase the room width."
            )
        if room.rect.depth_ft < min_depth_ft - 1e-6:
            raise ValueError(
                "Error: PROPORTION_VIOLATION. "
                f"layout_rules.minimum_room_dimensions.{room_type}.min_depth_ft={min_depth_ft:.1f} "
                f"but room_id='{room.room_id}' depth is {room.rect.depth_ft:.2f}ft. "
                "Increase the room depth."
            )
        area_sf = room.rect.width_ft * room.rect.depth_ft
        if min_area_sf is not None and area_sf < min_area_sf - 1e-6:
            raise ValueError(
                "Error: PROPORTION_VIOLATION. "
                f"layout_rules.minimum_room_dimensions.{room_type}.min_area_sf={min_area_sf:.1f} "
                f"but room_id='{room.room_id}' area is {area_sf:.2f}sf. "
                "Increase room area."
            )

    default_minimums: dict[RoomType, MinimumRoomDimension] = {
        "bedroom": MinimumRoomDimension(
            min_width_ft=10.0,
            min_depth_ft=11.0,
            min_area_sf=114.0,
        ),
        "bathroom": MinimumRoomDimension(
            min_width_ft=5.0,
            min_depth_ft=7.5,
            min_area_sf=37.0,
        ),
        "kitchen": MinimumRoomDimension(
            min_width_ft=9.0,
            min_depth_ft=8.0,
            min_area_sf=72.0,
        ),
        "living": MinimumRoomDimension(
            min_width_ft=9.5,
            min_depth_ft=6.5,
            min_area_sf=61.0,
        ),
        "open_living_kitchen": MinimumRoomDimension(
            min_width_ft=16.0,
            min_depth_ft=10.0,
            min_area_sf=160.0,
        ),
    }
    guideline_by_type = dict(default_minimums)
    guideline_by_type.update(layout_rules.minimum_room_dimensions)

    for room_type in ("bedroom", "bathroom", "kitchen", "living", "open_living_kitchen"):
        guideline = guideline_by_type.get(room_type)
        if guideline is None:
            continue
        for room in room_groups.get(room_type, []):
            _validate_room_minimums(
                room,
                room_type=room_type,
                min_width_ft=guideline.min_width_ft,
                min_depth_ft=guideline.min_depth_ft,
                min_area_sf=guideline.min_area_sf,
            )

    axis: LongAxis = layout_rules.long_axis

    def _axis_center(rooms: Sequence[RoomIntent]) -> float | None:
        if not rooms:
            return None
        vals: list[float] = []
        for room in rooms:
            center_x = room.rect.x_ft + (room.rect.width_ft / 2.0)
            center_y = room.rect.y_ft + (room.rect.depth_ft / 2.0)
            vals.append(center_x if axis == "x" else center_y)
        return sum(vals) / len(vals)

    bedroom_center = _axis_center(room_groups.get("bedroom", []))
    bathroom_center = _axis_center(room_groups.get("bathroom", []))
    if open_plan_required:
        living_center = _axis_center(room_groups.get("open_living_kitchen", []))
    else:
        living_center = _axis_center(
            (room_groups.get("living", []) or [])
            + (room_groups.get("kitchen", []) or [])
        )
    if (
        layout_rules.plumbing_core_required
        and bedroom_center is not None
        and bathroom_center is not None
        and living_center is not None
        and not (
            bedroom_center < bathroom_center < living_center
            or living_center < bathroom_center < bedroom_center
        )
    ):
        raise ValueError(
            "Error: PLUMBING_CORE_VIOLATION. The bathroom is not located between the bedroom "
            "and living space as required by your layout_rules. Move the bathroom to the center "
            "of the plan along the long axis."
        )

    wall_ids: set[str] = set()
    for wall in agent_output.walls_intent:
        if wall.wall_id in wall_ids:
            raise ValueError(f"Duplicate wall_id '{wall.wall_id}' in Agent2 output")
        wall_ids.add(wall.wall_id)
        _validate_local_point(
            f"Wall '{wall.wall_id}' start_local",
            wall.start_local.x_ft,
            wall.start_local.y_ft,
        )
        _validate_local_point(
            f"Wall '{wall.wall_id}' end_local",
            wall.end_local.x_ft,
            wall.end_local.y_ft,
        )
        if (
            abs(wall.start_local.x_ft - wall.end_local.x_ft) <= 1e-9
            and abs(wall.start_local.y_ft - wall.end_local.y_ft) <= 1e-9
        ):
            raise ValueError(f"Wall '{wall.wall_id}' has zero length")

    for opening in agent_output.openings_intent:
        if opening.wall_id not in wall_ids:
            raise ValueError(
                f"Opening '{opening.opening_id}' references unknown wall_id '{opening.wall_id}'"
            )
        _validate_local_point(
            f"Opening '{opening.opening_id}' anchor_local",
            opening.anchor_local.x_ft,
            opening.anchor_local.y_ft,
        )

    def _point_on_room_boundary(rect: LocalRect, point: LocalPoint) -> bool:
        x = point.x_ft
        y = point.y_ft
        on_left = abs(x - rect.x_ft) <= 1e-6 and rect.y_ft - 1e-6 <= y <= rect.max_y + 1e-6
        on_right = abs(x - rect.max_x) <= 1e-6 and rect.y_ft - 1e-6 <= y <= rect.max_y + 1e-6
        on_bottom = abs(y - rect.y_ft) <= 1e-6 and rect.x_ft - 1e-6 <= x <= rect.max_x + 1e-6
        on_top = abs(y - rect.max_y) <= 1e-6 and rect.x_ft - 1e-6 <= x <= rect.max_x + 1e-6
        return on_left or on_right or on_bottom or on_top

    door_openings = [opening for opening in agent_output.openings_intent if opening.opening_type == "door"]
    for room in agent_output.rooms:
        if room.room_type == "storage":
            continue
        if not any(_point_on_room_boundary(room.rect, door.anchor_local) for door in door_openings):
            raise ValueError(
                f"ROOM_DISCONNECTED: room '{room.room_id}' has no door opening on its boundary"
            )


def build_geometry_resolver_input(
    agent_2_input: Agent2Input,
    agent_2_output: Agent2Output,
    *,
    existing_structures_passthrough: list[ExistingStructure] | None = None,
) -> GeometryResolverInput:
    """
    Build deterministic geometry-resolver payload from validated Agent 2 artifacts.
    """
    ensure_sw_normalized(agent_2_input.site_context.input_coordinates_normalized_to_sw)
    validate_agent_2_output_against_input(agent_2_input, agent_2_output)

    payload = {
        "agent_1_output": agent_2_input.agent_1_output.model_dump(mode="json"),
        "agent_2_output": agent_2_output.model_dump(mode="json"),
        "site_context": agent_2_input.site_context.model_dump(mode="json"),
        "selected_zone": agent_2_input.selected_zone.model_dump(mode="json"),
        "selected_program": agent_2_input.selected_program.model_dump(mode="json"),
        "design_rules": agent_2_input.design_rules.model_dump(mode="json"),
        "existing_structures_passthrough": [
            s.model_dump(mode="json") for s in (existing_structures_passthrough or [])
        ],
        "input_coordinates_normalized_to_sw": True,
    }
    return GeometryResolverInput.model_validate(payload)


def build_conflict_geometry_resolver_input(
    agent_1_input: Agent1Input,
    agent_1_output: Agent1Output,
    *,
    input_coordinates_normalized_to_sw: bool = True,
) -> GeometryResolverInput:
    """
    Build resolver payload for conflict mode so deterministic drawing can still proceed.
    """
    if not agent_1_output.conflict_flag:
        raise ValueError("build_conflict_geometry_resolver_input requires conflict Agent1 output")
    ensure_sw_normalized(input_coordinates_normalized_to_sw)

    payload = {
        "agent_1_output": agent_1_output.model_dump(mode="json"),
        "agent_2_output": {
            "agent": "adu-designer-agent-2",
            "version": "1.0",
            "conflict_flag": True,
            "design_summary": {
                "program_id": "conflict",
                "zone_id": "conflict",
                "layout_type": "conflict",
            },
            "rooms": [],
            "walls_intent": [],
            "openings_intent": [],
            "notes": ["UPSTREAM_CONFLICT"],
        },
        "site_context": {
            "lot_width_ft": agent_1_input.site_metadata.lot_width_ft,
            "lot_depth_ft": agent_1_input.site_metadata.lot_depth_ft,
            "street_frontage": agent_1_input.site_metadata.street_frontage,
            "input_coordinates_normalized_to_sw": input_coordinates_normalized_to_sw,
        },
        "selected_zone": None,
        "selected_program": None,
        "design_rules": {
            "grid_step_ft": 0.5,
            "wall_thickness_options_ft": [0.35, 0.5],
            "max_retry_iteration": 1,
        },
        "existing_structures_passthrough": [
            s.model_dump(mode="json") for s in agent_1_input.existing_structures
        ],
        "input_coordinates_normalized_to_sw": True,
    }
    return GeometryResolverInput.model_validate(payload)


"""Canonical runtime contracts for Agent 1/Agent 2/Python handoffs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Sequence

from pydantic import BaseModel, ConfigDict, Field, model_validator

StreetFrontage = Literal["north", "south", "east", "west"]
OriginCorner = Literal["SW", "SE", "NW", "NE"]
PlacementStrategy = Literal["rear-left", "rear-right", "rear-center", "conflict"]
CandidateStrategy = Literal["rear-left", "rear-right", "rear-center"]
WallRole = Literal["front", "rear", "left", "right"]
TraceStatus = Literal["accepted", "rejected"]
RoomType = Literal["bedroom", "bathroom", "kitchen", "living", "circulation", "storage"]
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
    target_area_sf: float = Field(gt=0)
    adjacency: list[str] = Field(default_factory=list)


class WallIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    wall_id: str = Field(min_length=1)
    kind: WallKind
    start_ratio: RatioPoint
    end_ratio: RatioPoint
    thickness_ft: float = Field(gt=0)


class OpeningIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opening_id: str = Field(min_length=1)
    wall_id: str = Field(min_length=1)
    opening_type: OpeningType
    position_ratio_on_wall: float = Field(ge=0.0, le=1.0)
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
    selected_zone: SelectedZone
    selected_program: SelectedProgram
    design_rules: DesignRules
    existing_structures_passthrough: list[ExistingStructure] = Field(default_factory=list)
    input_coordinates_normalized_to_sw: bool

    @model_validator(mode="after")
    def validate_normalized_flag(self) -> "GeometryResolverInput":
        if not self.input_coordinates_normalized_to_sw:
            raise ValueError("geometry resolver requires input_coordinates_normalized_to_sw=true")
        if not self.agent_1_output.conflict_flag:
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
    }
    return Agent2Input.model_validate(payload)


def validate_agent_2_output_against_input(agent_input: Agent2Input, agent_output: Agent2Output) -> None:
    """Cross-validate Agent 2 output IDs against Agent 2 input contract."""

    if agent_output.conflict_flag:
        return
    if agent_output.design_summary.zone_id != agent_input.selected_zone.zone_id:
        raise ValueError("Agent2 output zone_id does not match Agent2 input selected_zone")
    if agent_output.design_summary.program_id != agent_input.selected_program.program_id:
        raise ValueError("Agent2 output program_id does not match Agent2 input selected_program")


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


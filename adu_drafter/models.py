"""Pydantic data contracts for the 2D ADU planning pipeline."""

from __future__ import annotations

from typing import List

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Point2D(BaseModel):
    """A strict 2D coordinate in the X/Y plane."""

    model_config = ConfigDict(extra="forbid")

    x: float
    y: float


class BoundingBox2D(BaseModel):
    """Axis-aligned 2D box described by min/max X/Y extents."""

    model_config = ConfigDict(extra="forbid")

    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @model_validator(mode="after")
    def validate_bounds(self) -> "BoundingBox2D":
        if self.max_x <= self.min_x:
            raise ValueError("max_x must be greater than min_x")
        if self.max_y <= self.min_y:
            raise ValueError("max_y must be greater than min_y")
        return self


class Setbacks(BaseModel):
    """2D setback offsets measured inward from lot boundaries."""

    model_config = ConfigDict(extra="forbid")

    front: float = Field(ge=0)
    rear: float = Field(ge=0)
    left: float = Field(ge=0)
    right: float = Field(ge=0)


class ExistingStructure(BaseModel):
    """Existing structure footprint with required separation buffer."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    separation_req: float = Field(default=6.0, ge=0.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ExistingStructure":
        if self.x_max <= self.x_min:
            raise ValueError("x_max must be greater than x_min")
        if self.y_max <= self.y_min:
            raise ValueError("y_max must be greater than y_min")
        return self


class SiteInput(BaseModel):
    """Hardcoded site and zoning inputs for deterministic geometry."""

    model_config = ConfigDict(extra="forbid")

    lot_width: float = Field(gt=0)
    lot_depth: float = Field(gt=0)
    setbacks: Setbacks
    existing_structures: List[ExistingStructure] = Field(default_factory=list)
    existing_house: BoundingBox2D | None = None
    separation_distance: float = Field(default=6.0, ge=0.0)

    @model_validator(mode="after")
    def normalize_legacy_existing_house(self) -> "SiteInput":
        """
        Backward-compatible bridge:
        - preferred input: existing_structures[]
        - legacy input: existing_house + separation_distance
        """
        if self.existing_structures:
            return self
        if self.existing_house is None:
            raise ValueError("SiteInput requires existing_structures (or legacy existing_house)")
        self.existing_structures = [
            ExistingStructure(
                name="Primary Residence",
                x_min=self.existing_house.min_x,
                y_min=self.existing_house.min_y,
                x_max=self.existing_house.max_x,
                y_max=self.existing_house.max_y,
                separation_req=self.separation_distance,
            )
        ]
        return self


class WallSegment(BaseModel):
    """Linear wall segment represented in 2D by start/end points."""

    model_config = ConfigDict(extra="forbid")

    start: Point2D
    end: Point2D
    thickness: float = Field(gt=0)
    layer: str = Field(min_length=1)


class BlockInsertion(BaseModel):
    """Static CAD block insertion instruction for the drafter."""

    model_config = ConfigDict(extra="forbid")

    block_name: str = Field(min_length=1)
    x: float
    y: float
    rotation: float = 0.0
    layer: str = Field(min_length=1)
    xscale: float = 1.0
    yscale: float = 1.0


class ADUDesignBrief(BaseModel):
    """Contract between the reasoning layer and deterministic drafter."""

    model_config = ConfigDict(extra="forbid")

    target_sqft: float = Field(gt=0)
    bedrooms: int = Field(ge=0)
    bathrooms: int = Field(ge=0)
    walls: List[WallSegment] = Field(default_factory=list)
    blocks: List[BlockInsertion] = Field(default_factory=list)

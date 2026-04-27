# Python Geometry Resolver Spec (Deterministic)
Version 1.0 | April 2026

## Purpose

Define the deterministic Python service that converts approved ADU design intent
into fully resolved 2D drawing geometry and DXF-ready instructions.

This document is derived from the prior Agent 2 arithmetic prompt but is now
owned by Python for precision and testability.

## Scope

- 2D only (X/Y)
- Rectangular lots only (PoC)
- Detached ADU Type D-3 flow
- Deterministic coordinate resolution, annotation geometry, and layer assignment
- No zoning interpretation (already done by Agent 1 and validated upstream)

## Required Inputs

Top-level input contract:

```json
{
  "input_coordinates_normalized_to_sw": true,
  "site_input": { "...": "canonical site schema from docs/canonical-schemas.md" },
  "agent_1_decision": { "...": "canonical Agent 1 output schema" },
  "agent_2_design_brief": { "...": "canonical Agent 2 output schema" }
}
```

Hard requirements:

1. `input_coordinates_normalized_to_sw` MUST exist and be `true`.
2. All schemas MUST pass Pydantic validation before coordinate resolution starts.
3. If any required field is missing, the resolver MUST fail deterministically with
   machine-readable errors and produce no DXF output.

## Core Responsibility Split

Python resolver owns:

- absolute coordinate computation
- bounding boxes and rectangle corner derivation
- layer assignments and linetype defaults
- setback and separation zone geometry
- label anchor points
- dimension line geometry
- geometry anomaly flags
- final `dxf_instructions.json` and DXF entity creation

Python resolver does not own:

- zoning decision logic
- placement strategy selection
- interior design judgment

## Coordinate System

- Units: feet
- Origin: SW corner `(0, 0)`
- +X eastward
- +Y northward

All downstream coordinates MUST remain in this system.

## Geometry Derivation Rules

### Lot Boundary

- SW: `(0, 0)`
- SE: `(lot_width_ft, 0)`
- NE: `(lot_width_ft, lot_depth_ft)`
- NW: `(0, lot_depth_ft)`
- Closed polyline order: SW → SE → NE → NW → SW

### Setback Boundary

- Inset 4 ft from all lot lines (PoC fixed value)
- SW: `(4, 4)`
- SE: `(lot_width_ft - 4, 4)`
- NE: `(lot_width_ft - 4, lot_depth_ft - 4)`
- NW: `(4, lot_depth_ft - 4)`

### Existing Structures

For each structure:

- SW: `(offset_from_origin_x_ft, offset_from_origin_y_ft)`
- NE: `(offset_x + width_ft, offset_y + depth_ft)`
- Closed points list generated from SW/NE
- Label anchor at rectangle centroid

### ADU Footprint

Derived from approved Agent 1 placement + selected program footprint:

- `side_placement = left`:
  - `adu_sw_x = side_setback_ft`
- `side_placement = right`:
  - `adu_sw_x = lot_width_ft - side_setback_ft - adu_width_ft`
- `side_placement = centered`:
  - `adu_sw_x = (lot_width_ft - adu_width_ft) / 2`
- `adu_sw_y = lot_depth_ft - rear_setback_ft - adu_depth_ft`
- `adu_ne_x = adu_sw_x + adu_width_ft`
- `adu_ne_y = adu_sw_y + adu_depth_ft`

### Separation Zone (No Clipping Rule)

Expand ADU bbox by minimum structure separation:

- `sep_sw_x = adu_sw_x - min_structure_separation_ft`
- `sep_sw_y = adu_sw_y - min_structure_separation_ft`
- `sep_ne_x = adu_ne_x + min_structure_separation_ft`
- `sep_ne_y = adu_ne_y + min_structure_separation_ft`

**Do not clip** separation rectangle to lot boundary.
If bounds exceed lot extents, keep full coordinates and append geometry flags.

### ADU Label Anchors

- Primary centroid:
  - `cx = adu_sw_x + adu_width_ft / 2`
  - `cy = adu_sw_y + adu_depth_ft / 2`
- Split label text by `" | "` into lines
- `line_spacing_ft = 1.5`
- `text_height_ft = 0.8`
- Top line:
  - `top_y = cy + ((n_lines - 1) / 2) * line_spacing_ft`

### Dimension Lines

Always:

1. LOT_WIDTH
2. LOT_DEPTH

Only when `conflict_flag == false`:

3. ADU_WIDTH
4. ADU_DEPTH

Conflict mode explicitly omits ADU dimension entries.

### Street Label

Anchor depends on `street_frontage`:

- south: `(lot_width_ft / 2, -4)`
- north: `(lot_width_ft / 2, lot_depth_ft + 4)`
- east: `(lot_width_ft + 4, lot_depth_ft / 2)`
- west: `(-4, lot_depth_ft / 2)`

### Separation Compliance Markers

For each Agent 1 separation record:

- match structure by label
- centroid_x = structure centroid x
- circle center = `(centroid_x, structure_sw_y - 4)`
- text anchor = `(centroid_x, structure_sw_y - 7)`
- green if compliant else red

## Conflict Handling

If `agent_1_decision.conflict_flag == true`:

- Still output:
  - lot boundary
  - setback boundary
  - existing structures
  - separation compliance markers
  - lot-only dimensions (LOT_WIDTH and LOT_DEPTH)
- Set ADU-specific geometry to `null`:
  - `adu_elements = null`
- Output `conflict_notice` lines at lot center offsets.

## Precision Rules

- Round output numeric fields to max 4 decimal places.
- Maintain deterministic rounding policy (e.g., `round(value, 4)`).

## Geometry Flags

Populate `geometry_flags[]` when anomalies are detected, for example:

- `SEPARATION_ZONE_EXTENDS_WEST_OF_LOT`
- `SEPARATION_ZONE_EXTENDS_NORTH_OF_LOT`
- `ADU_FOOTPRINT_OUTSIDE_LOT`
- `NEGATIVE_OR_ZERO_DIMENSION_INPUT`

Flags do not imply automatic clipping.

## Output Artifact

Resolver writes:

1. `dxf_instructions.json` (fully resolved deterministic geometry payload)
2. `generated_adu.dxf` via ezdxf from the instructions payload

No additional runtime geometry decisions are allowed in the DXF writer.

## Testing Requirements

Minimum deterministic tests:

1. Nominal feasible case (rear-left placement)
2. Conflict case (no compliant zone)
3. Right and centered side placements
4. Separation zone outside lot (flags expected; no clipping)
5. Missing `input_coordinates_normalized_to_sw` (hard fail)
6. Numeric precision enforcement (max 4 decimals)


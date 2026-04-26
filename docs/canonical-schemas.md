# ADU PoC Canonical Schemas
Version 1.0 | April 2026

This document is the single source of truth for data contracts between:

1. Agent 1 (Site Decision Agent)
2. Agent 2 (ADU Designer Agent)
3. Python Geometry Resolver / DXF engine

If a prompt conflicts with this document, this document wins.

---

## Global Rules

- 2D only (X/Y). No Z/elevation fields.
- Rectangular lots only in PoC.
- Units are feet.
- Coordinates in all downstream contracts are SW-origin unless explicitly noted.
- LLM agents must not invent missing dimensions.
- Deterministic geometry math and DXF serialization are Python responsibilities.

---

## Schema A: `agent_1_input.json`

```json
{
  "site_metadata": {
    "lot_id": "string",
    "rectangular_lot": true,
    "lot_width_ft": 0.0,
    "lot_depth_ft": 0.0,
    "street_frontage": "north|south|east|west",
    "origin_corner": "SW|SE|NW|NE"
  },
  "existing_structures": [
    {
      "id": "string",
      "label": "string",
      "is_primary_dwelling": true,
      "offset_from_origin_x_ft": 0.0,
      "offset_from_origin_y_ft": 0.0,
      "width_ft": 0.0,
      "depth_ft": 0.0
    }
  ],
  "primary_dwelling_walls": [
    {
      "wall_label": "string",
      "wall_role": "front|rear|left|right"
    }
  ],
  "candidate_zones": [
    {
      "zone_id": "string",
      "strategy": "rear-left|rear-right|rear-center",
      "zone_polygon_sw_origin": [[0.0, 0.0]],
      "check_results": {
        "check_1_rear_setback": true,
        "check_2_side_setback": true,
        "check_3_front_constraint": true,
        "check_4_primary_separation": true,
        "check_5_other_structure_separation": true
      },
      "metrics": {
        "rear_setback_ft": 4.0,
        "side_setback_ft": 4.0,
        "clearance_to_primary_ft": 0.0
      },
      "failed_reason_codes": []
    }
  ],
  "program_catalog": [
    {
      "program_id": "string",
      "bedrooms": 1,
      "bathrooms": 1,
      "target_area_sf": 500.0,
      "footprint_width_ft": 20.0,
      "footprint_depth_ft": 30.0
    }
  ],
  "client_request": {
    "target_size_sf": 500.0,
    "bedrooms_preference": 1,
    "bathrooms_preference": 1,
    "transit_proximity": false
  }
}
```

---

## Schema B: `agent_1_output.json`

```json
{
  "agent": "site-decision-agent-1",
  "version": "1.0",
  "conflict_flag": false,
  "conflict_reasons": [],
  "decision_summary": {
    "selected_strategy": "rear-left|rear-right|rear-center|conflict",
    "selected_zone_id": "string|null",
    "selected_program_id": "string|null",
    "primary_dwelling_rear_wall_label": "string|null"
  },
  "compliance_trace": [
    {
      "zone_id": "string",
      "strategy": "rear-left|rear-right|rear-center",
      "check_results": {
        "check_1_rear_setback": true,
        "check_2_side_setback": true,
        "check_3_front_constraint": true,
        "check_4_primary_separation": true,
        "check_5_other_structure_separation": true
      },
      "status": "accepted|rejected",
      "reason_codes": []
    }
  ],
  "for_agent_2": {
    "zone_id": "string|null",
    "program_id": "string|null",
    "strategy": "rear-left|rear-right|rear-center|conflict",
    "constraints_profile_id": "string"
  },
  "notes": []
}
```

Conflict mode:
- `selected_strategy = "conflict"`
- `selected_zone_id = null`
- `selected_program_id = null`

---

## Schema C: `agent_2_input.json`

```json
{
  "agent_1_output": {},
  "site_context": {
    "lot_width_ft": 0.0,
    "lot_depth_ft": 0.0,
    "street_frontage": "north|south|east|west",
    "input_coordinates_normalized_to_sw": true
  },
  "selected_zone": {
    "zone_id": "string",
    "zone_polygon_sw_origin": [[0.0, 0.0]]
  },
  "selected_program": {
    "program_id": "string",
    "bedrooms": 1,
    "bathrooms": 1,
    "target_area_sf": 500.0,
    "footprint_width_ft": 20.0,
    "footprint_depth_ft": 30.0
  },
  "design_rules": {
    "grid_step_ft": 0.5,
    "wall_thickness_options_ft": [0.35, 0.5],
    "max_retry_iteration": 3
  }
}
```

If `input_coordinates_normalized_to_sw != true`, processing must fail deterministically.

---

## Schema D: `agent_2_output.json`

Agent 2 is a design-intent generator, not a coordinate compiler.
To avoid Python-side packing/optimization, Agent 2 must emit explicit zone-local primitives.

```json
{
  "agent": "adu-designer-agent-2",
  "version": "1.1",
  "conflict_flag": false,
  "design_summary": {
    "program_id": "string",
    "zone_id": "string",
    "layout_type": "string"
  },
  "rooms": [
    {
      "room_id": "string",
      "room_type": "bedroom|bathroom|kitchen|living|circulation|storage",
      "target_area_sf": 0.0,
      "rect": {
        "x_ft": 0.0,
        "y_ft": 0.0,
        "width_ft": 0.0,
        "depth_ft": 0.0
      },
      "adjacency": []
    }
  ],
  "walls_intent": [
    {
      "wall_id": "string",
      "kind": "exterior|interior",
      "start_local": { "x_ft": 0.0, "y_ft": 0.0 },
      "end_local": { "x_ft": 10.0, "y_ft": 0.0 },
      "thickness_ft": 0.5
    }
  ],
  "openings_intent": [
    {
      "opening_id": "string",
      "wall_id": "string",
      "opening_type": "door|window",
      "anchor_local": { "x_ft": 2.5, "y_ft": 0.0 },
      "width_ft": 3.0
    }
  ],
  "notes": []
}
```

Deterministic validation expectations:
- all local geometry must be inside selected zone extents
- all coordinates must snap to `design_rules.grid_step_ft`
- room rectangles must not overlap
- every opening anchor must lie on its host wall segment
- every opening width must be less than or equal to host wall length

---

## Schema E: `geometry_resolver_input.json` (Python)

```json
{
  "agent_1_output": {},
  "agent_2_output": {},
  "site_context": {},
  "existing_structures_passthrough": [],
  "input_coordinates_normalized_to_sw": true
}
```

---

## Schema F: `dxf_instructions.json` (Python output)

Python emits canonical drawable geometry:
- lot boundary
- setback boundary
- existing structures
- ADU footprint and interior walls/openings
- labels and dimensions
- geometry flags

In conflict mode:
- include lot + setback + existing structures + conflict notice
- omit ADU-specific dimensions (`ADU_WIDTH`, `ADU_DEPTH`)

---

## Versioning

- Each schema payload must include `version`.
- Any breaking field change requires version bump and migration note in this document.

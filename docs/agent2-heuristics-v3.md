# Agent 2 — Layout Behavioral Contract (v3)

> **Authority Note:** `adu_drafter/contracts.py` and `layout_rules` are the canonical enforcement source. This document is Agent 2 guidance for first-pass quality and retry avoidance.  
> **Current behavior:** hard-rule violations trigger retry/failure; soft-rule deductions are telemetry-only and non-blocking.  
> **Target behavior (future):** orchestrator-level Best-of-N selection by quality score.

---

## 1. Hard Rules (Binary Pass/Fail)

Violations of these rules are treated as invalid outputs and must be corrected on retry.

### H1 — Geometric Integrity (Hard Scope)
- Room polygons must have **zero positive overlap area**.
- All room geometry must be contained inside the selected footprint bounds.

Notes:
- Exterior shell loop completeness/closure is **not currently enforced as hard** in Phase 1.
- Keep overlap/containment as the reliability-critical geometry gate.

### H2 — Program Fulfillment (Schema-Exact Room Types)
- Use only runtime `RoomType` values:
  - `bedroom`
  - `bathroom`
  - `living`
  - `kitchen`
  - `open_living_kitchen`
  - `circulation`
  - `storage`
- Do not emit unsupported labels/types such as `closet`, `laundry`, `dining`, or title-cased forms.
- Room counts must satisfy **minimum required counts** from `layout_rules.required_room_counts` (`>=`, not exact-equality unless explicitly encoded as such).

### H3 — Minimum Room Dimensions
- Enforce `layout_rules.minimum_room_dimensions` for each listed room type.
- Width/depth and optional minimum area thresholds are hard constraints.

### H4 — Entry Rule (Hard)
- At least one exterior door must exist.
- Primary exterior entry must open into a public room:
  - `living`, `kitchen`, or `open_living_kitchen`.
- Exterior entry must not open directly into:
  - `bedroom`, `bathroom`, or `circulation`.

### H5 — Safe Bathroom/Kitchen Circulation (Hard)
- Bathroom doors must not open directly into:
  - `kitchen` or `open_living_kitchen`.
- Every non-`storage` room must have at least one door opening on its boundary (connectivity hard gate).

### H6 — Plumbing Core Ordering (Hard when enabled)
- If `layout_rules.plumbing_core_required=true`, bathroom zone centroid must lie between bedroom and living/open-living zone centroids along `layout_rules.long_axis`.

---

## 2. Soft Rules (Telemetry-Only, Non-Blocking)

Soft rules improve plan quality but do not trigger retry/failure in current architecture.

### S1 — Room Aspect Ratio
- Prefer balanced room proportions.
- Penalize strongly elongated rooms.

### S2 — Area Distribution
- Keep area shares per room type within practical target bands.

### S3 — Living/Kitchen Relationship
- Prefer shared-edge adjacency or open-plan merge where appropriate.

### S4 — Bedroom/Bathroom Access Quality
- Prefer short, direct adjacency between bedroom and bathroom.

### S5 — Plumbing Clustering
- Prefer wet-room clustering to reduce plumbing complexity.

### S6 — Guest Circulation Path
- Prefer bathroom access from public zone without crossing bedroom.

### S7 — Entry Transition Quality
- Prefer a small transition buffer at entry where feasible.

### S8 — Exterior Wall Access
- Prefer exterior wall adjacency for bedrooms/living (natural-light quality signal).

### S9 — Hallway Efficiency
- Prefer minimal circulation area in compact ADUs.

---

## 3. Retry/Error Guidance Conventions

Current retry loop behavior uses actionable validator error strings. Agent 2 should treat these as rule-targeted corrections.

Examples:
- `Error: OPEN_PLAN_REQUIRED ... Merge living and kitchen into one open_living_kitchen room.`
- `Error: PROPORTION_VIOLATION ... Increase width/depth/area.`
- `Error: PLUMBING_CORE_VIOLATION ... Move bathroom to center zone along long axis.`
- `Error: ENTRY_VIOLATION ... Move entry to public room.`
- `Error: CIRCULATION_VIOLATION ... Relocate bathroom door away from kitchen/open-living.`

Structured machine-readable violation payloads are a future enhancement and not required for Phase 1.

---

## 4. Agent 2 Pre-Flight Checklist

Before final output:

- [ ] No positive room overlap.
- [ ] All geometry inside footprint bounds and on-grid.
- [ ] Only valid runtime room types are used.
- [ ] `layout_rules.required_room_counts` minimums are met.
- [ ] `layout_rules.minimum_room_dimensions` thresholds are met.
- [ ] Exterior entry exists and opens into `living|kitchen|open_living_kitchen`.
- [ ] Exterior entry does not open into `bedroom|bathroom|circulation`.
- [ ] No bathroom door opens directly into `kitchen|open_living_kitchen`.
- [ ] If enabled, plumbing core ordering is satisfied along `layout_rules.long_axis`.

---

## 5. Best-of-N Selection (Now Supported)

- **Current default:** first valid success is accepted when only one Agent 2 output is provided.
- **Current optional mode:** orchestrator supports Best-of-N candidate selection (`--agent-2-candidate-outputs` + `--best-of-n`) and picks the highest soft score among hard-valid candidates.
- **Invariant:** hard-rule validity gates remain strict and are never relaxed by soft scoring.

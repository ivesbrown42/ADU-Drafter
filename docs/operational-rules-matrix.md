# ADU Operational Rules Matrix (Phase 1)

This matrix defines what affects reliability-critical pipeline behavior versus what is telemetry-only quality scoring.

## Scope and goals

- Preserve deterministic pipeline reliability.
- Keep retries/failures tied only to core geometry and connectivity validity.
- Capture richer layout-quality feedback in reports without blocking DXF generation.
- Explicitly **exclude** Section 6 (windows) and Section 7 (door swing semantics) for this phase.

## Rule categories

### HARD rules (trigger retries / failures)

These are enforced in `validate_agent_2_output_against_input(...)` and continue to drive orchestrator retries:

1. Geometry validity
   - Program footprint must fit selected zone.
   - Room rectangles must remain inside footprint bounds.
   - Room rectangles must not overlap.
   - Wall/opening points must be within zone-local bounds and snapped to grid.
   - Opening anchors must lie on host wall segments.

2. Required program presence
   - Required room counts for:
     - `bedroom` (from selected program)
     - `bathroom` (from selected program)
     - `kitchen` (>= 1)
     - `living` (>= 1)

3. Basic connectivity
   - Every non-storage room must have at least one door opening on its boundary.

4. Exterior shell consistency
   - Exterior wall intents must form the required closed orthogonal loop.

### SOFT rules (telemetry-only, no retries/failures)

Implemented via `adu_drafter.quality_scoring.score_agent_2_layout(...)` and written to eval outputs as advisory deductions:

- Wall/circulation budget heuristics and room area utilization targets.
- Open-plan recommendation vs living-kitchen partitioning.
- Zoning grammar / long-axis sequencing:
  - bedroom zone
  - plumbing core
  - living zone
- Room dimension heuristics (bed/bath/kitchen/living/circulation).
- Area share target ranges by room type and program shape.
- Adjacency quality checks:
  - plumbing core clustering
  - bath-kitchen door relationship
  - entry door into living zone
  - bedroom/living/kitchen exterior-wall access preferences
  - selected 2BR access/clustering preferences

### Deferred rules (not implemented in Phase 1)

- Section 6: window placement rules.
- Section 7: door swing rules and directional semantics.

## Telemetry output contract

For successful eval attempts with Agent 2 payloads, `scripts/run_evals.py` adds:

- `attempts[i].quality_telemetry.score`
- `attempts[i].quality_telemetry.status`
- `attempts[i].quality_telemetry.total_penalty`
- `attempts[i].quality_telemetry.deductions[]` (code, penalty, description)
- `attempts[i].quality_telemetry.metadata` (footprint/area/utilization context)

Additionally, top-level report summary includes:

- `summary.quality_telemetry`
  - `cases_with_quality_telemetry`
  - `average_score`
  - `status_breakdown`
  - `top_deduction_codes`

## Notes on reliability

- Soft-rule scoring is read-only and wrapped defensively in eval harness.
- Scoring errors are recorded as telemetry errors and do not alter pass/fail outcomes.
- Orchestrator retry/failure behavior remains unchanged by scoring.

# ADU PoC Master Orchestration
Version 1.0 | April 2026

## Goal

Run a strict 2D-only two-agent pipeline where:

1. Agent 1 chooses ADU placement zone + program type from complete site plan geometry.
2. Agent 2 generates interior ADU design intent constrained to Agent 1 output.
3. Deterministic Python validation gates every handoff.
4. Final output artifact is always a DXF file (`generated_adu.dxf`).

No 3D/Z-axis logic is permitted anywhere in this flow.

## Agent Roles

### Agent 1 — Site Decision Agent

**Purpose:** Placement/program decision only.

Inputs:
- Complete site plan geometry (rectangular lots only)
- Existing structures (including primary dwelling wall labels)
- Program options / client requirements

Outputs:
- Selected placement strategy (`rear-left`, `rear-right`, `rear-center`, or `conflict`)
- Selected ADU program type (for example `1BR` or `2BR`)
- Chosen build zone polygon (or zone identifier)
- Constraint handoff package for Agent 2
- Conflict reasons when no compliant placement exists

Must not output:
- CAD/DXF primitives
- Interior room plans
- Invented dimensions

### Agent 2 — ADU Designer Agent

**Purpose:** Design ADU plan intent inside Agent 1's approved envelope.

Inputs:
- Agent 1 placement/program output
- Build-zone geometry and hard constraints
- Grid definition and snapping rules
- Program requirements

Outputs:
- ADU design brief JSON for deterministic drafting
- Walls/partitions/openings and optional room labels
- Zero geometry outside approved build zone

Must not output:
- Raw DXF commands
- Any geometry violating Agent 1 constraints

## Deterministic Ownership (Python)

Python services remain source of truth for:
- Geometry computations (setbacks, separations, overlaps, containment)
- Grid snap enforcement
- Schema validation
- Compliance gate pass/fail decisions
- DXF drafting via `ezdxf`

LLMs propose intent; Python accepts/rejects and drafts.

## End-to-End Sequence

1. **Preprocess Site**
   - Parse normalized site plan input
   - Validate completeness (no missing geometry dimensions)
   - Build derived geometry used for compliance checks

2. **Run Agent 1**
   - Select candidate placement/program
   - Emit placement decision contract

3. **Validate Agent 1 Output**
   - Pydantic schema check
   - Geometry compliance check
   - If invalid, return structured errors and retry Agent 1 (bounded retries)
   - If still invalid, stop with deterministic conflict report

4. **Run Agent 2**
   - Generate ADU design intent constrained by Agent 1 decision

5. **Validate Agent 2 Output**
   - Pydantic schema check
   - Build-zone containment
   - Grid snap + collision + topology checks
   - If invalid, return structured errors and retry Agent 2 (bounded retries)

6. **Draft DXF**
   - Convert validated design brief to layers/entities in `ezdxf`
   - Write `generated_adu.dxf`

7. **Emit Artifacts**
   - Final decision JSON (Agent 1)
   - Final design brief JSON (Agent 2)
   - QA reports
   - DXF output

## Retry Policy (PoC Default)

- Max retries per agent: 3
- Retry only with structured validation errors (never with freeform prose)
- If retries exhausted, emit deterministic failure artifact with reasons

## Required Contracts

- `site_input.json` (complete rectangular site plan + wall labels)
- `agent_1_decision.json` (placement/program)
- `agent_2_design_brief.json` (design intent)
- `qa_report_agent_1.json`
- `qa_report_agent_2.json`
- `generated_adu.dxf`

## Scope Boundaries (PoC)

- Rectangular lots only
- Type D-3 detached ADU pathway only
- 2D plan generation only
- No dynamic blocks
- No direct LLM-to-DXF writing

# ADU PoC Master Orchestration
Version 1.1 | April 2026

## Goal

Run a strict 2D-only two-agent pipeline where:

1. Agent 1 chooses ADU placement zone + program type from complete site plan geometry.
2. Agent 2 generates interior ADU design intent constrained to Agent 1 output.
3. Deterministic Python validation gates every handoff.
4. Final output artifact is always a DXF file (`generated_adu.dxf`).

No 3D/Z-axis logic is permitted anywhere in this flow.

## Canonical Contracts (Read First)

All pipeline steps MUST conform to:

- `docs/canonical-schemas.md`
- `docs/python-geometry-resolver-spec.md`

If any agent prompt conflicts with those docs, the canonical schema and Python resolver spec win.

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
- Deterministic `design_rules.layout_heuristics` from Python contract builder

Outputs:
- ADU interior design intent JSON (`agent_2_design_brief`)
- Grid-aligned walls/partitions/openings and optional room labels
- No absolute lot-coordinate resolution (that belongs to Python)

Must not output:
- Raw DXF commands
- Any geometry violating Agent 1 constraints
- Fully resolved lot-absolute drafting coordinates

## Deterministic Ownership (Python)

Python services remain source of truth for:
- Geometry computations (setbacks, separations, overlaps, containment)
- Grid snap enforcement
- Schema validation
- Compliance gate pass/fail decisions
- Geometry resolution into absolute drawing coordinates
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
   - Use `design_rules.layout_heuristics` as required preflight guidance before final JSON emission

5. **Validate Agent 2 Output**
   - Pydantic schema check
   - Build-zone containment
   - Grid snap + collision + topology checks
   - If invalid, return structured errors and retry Agent 2 (bounded retries)

6. **Resolve Geometry (Python)**
   - Convert validated design brief into deterministic absolute drawing instructions
   - Apply conflict-mode dimension rules and geometry flags per resolver spec

7. **Draft DXF**
   - Convert resolved instructions to layers/entities in `ezdxf`
   - Write `generated_adu.dxf`

8. **Emit Artifacts**
   - Final decision JSON (Agent 1)
   - Final design brief JSON (Agent 2)
   - Deterministic resolved drawing instruction JSON
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
- `resolved_drawing_instructions.json` (Python-generated absolute drawing instructions)
- `qa_report_agent_1.json`
- `qa_report_agent_2.json`
- `generated_adu.dxf`

## Scope Boundaries (PoC)

- Rectangular lots only
- Type D-3 detached ADU pathway only
- 2D plan generation only
- No dynamic blocks
- No direct LLM-to-DXF writing

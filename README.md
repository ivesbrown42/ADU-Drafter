# ADU-Drafter

2D-only Proof of Concept pipeline for generating a LA ADU floor plan DXF.

## Architecture

This repository enforces strict decoupling:

- **Reasoning layer (LLM):** outputs only structured JSON (`ADUDesignBrief`).
- **Execution layer (Python):** deterministically validates geometry and drafts DXF.

No 3D or Z-axis logic is used in this phase.

## Project Structure

- `adu_drafter/models.py` – Pydantic schemas for inputs/contracts.
- `adu_drafter/contracts.py` – canonical Agent 1/Agent 2/Python runtime contracts + handoff validators.
- `adu_drafter/geometry_engine.py` – Shapely buildable-area and QA checks.
- `adu_drafter/drafter.py` – ezdxf drafting engine using `template.dxf`.
- `adu_drafter/main.py` – pipeline entrypoint and LLM integration seam.
- `data/site_input.json` – hardcoded site + setback input.
- `data/manual_design_brief.json` – deterministic design brief sample.
- `docs/canonical-schemas.md` – canonical Agent 1 → Agent 2 → Python JSON contracts.
- `docs/python-geometry-resolver-spec.md` – deterministic geometry compiler spec for Python (not an LLM prompt).
- `prompts/agent-1-site-decision.md` – Agent 1 prompt (site analysis + placement decision only).
- `prompts/agent-2-adu-designer.md` – Agent 2 prompt (interior design intent only).
- `prompts/master-orchestration.md` – master contract for Agent 1 → Agent 2 sequencing.

## Quick Start

1. Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

2. Ensure `template.dxf` exists at `data/template.dxf`.
   - Must include static (flattened) block definitions.
   - Dynamic blocks are intentionally unsupported.
   - For this PoC scaffold, generate a starter template with:

```bash
python3 scripts/create_template.py
```

3. Run pipeline:

```bash
python3 -m adu_drafter.main \
  --site-input data/site_input.json \
  --design-brief data/manual_design_brief.json \
  --template data/template.dxf \
  --output generated_adu.dxf
```

If QA passes, `generated_adu.dxf` is written for Rayon import.

## Contract Validation Helpers

`adu_drafter/contracts.py` includes strict runtime validators for the two-agent pipeline:

- `load_agent_1_output(path)` – validates Agent 1 output contract.
- `build_agent_2_input(...)` – builds a normalized Agent 2 input payload.
- `load_agent_2_output(path)` – validates Agent 2 output contract.
- `build_geometry_resolver_input(...)` – merges validated payloads for deterministic Python geometry resolution.

These helpers enforce canonical schema rules, including:

- `input_coordinates_normalized_to_sw` must be `true`
- Agent 2 `zone_id/program_id` must match Agent 1 decision
- conflict-mode consistency checks

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
- `adu_drafter/geometry_resolver.py` – deterministic absolute-geometry resolver from validated handoffs.
- `adu_drafter/geometry_engine.py` – Shapely buildable-area and QA checks.
- `adu_drafter/drafter.py` – ezdxf drafting engine (brief-based and instruction-payload renderers).
- `adu_drafter/run_pipeline.py` – one-command Agent1 -> Agent2 -> resolver -> DXF runner.
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

## Geometry Resolver

`adu_drafter/geometry_resolver.py` converts validated `GeometryResolverInput` into
deterministic absolute drawing instructions.

Outputs include:

- lot boundary
- setback boundary
- existing structures
- ADU footprint/separation zone/labels (when non-conflict)
- dimensions (conflict mode omits `ADU_WIDTH` and `ADU_DEPTH`)
- street label
- separation compliance markers
- `geometry_flags` (no clipping behavior for separation zone)

CLI example:

```bash
python3 -m adu_drafter.geometry_resolver \
  --resolver-input data/geometry_resolver_input.json \
  --output data/resolved_drawing_instructions.json
```

## Orchestrator Entry Point

`adu_drafter/orchestrate.py` wires the canonical handoff flow:

1. load/validate `agent_1_input.json`
2. load/validate `agent_1_output.json`
3. cross-validate Agent 1 output against Agent 1 input
4. if conflict: emit conflict artifact and stop before Agent 2
5. otherwise build Agent 2 input, validate Agent 2 output, and emit:
   - `geometry_resolver_input.json`

Schema retry behavior:

- `--schema-retries` controls bounded retries for Agent 2 output schema/contract failures.
- On failure, orchestrator prints structured validation errors and retries loading the corrected artifact.
- If retries are exhausted, orchestration exits non-zero with deterministic error text.

Example:

```bash
python3 -m adu_drafter.orchestrate \
  --agent-1-input data/agent_1_input.json \
  --agent-1-output data/agent_1_output.json \
  --agent-2-output data/agent_2_output.json \
  --schema-retries 3 \
  --resolver-output data/geometry_resolver_input.json
```

## Deterministic DXF Renderer From Resolved Instructions

Render final DXF directly from `resolved_drawing_instructions.json`:

```bash
python3 -m adu_drafter.drafter \
  --instructions data/resolved_drawing_instructions.json \
  --template data/template.dxf \
  --output generated_adu_from_instructions.dxf \
  --floorplan-origin-x 100 \
  --floorplan-origin-y 0
```

This path does not depend on LLMs once contracts are validated.

`--floorplan-origin-x` / `--floorplan-origin-y` let you place the enlarged
floor-plan detail safely outside the site-plan extents in the same modelspace.

## One-Command End-to-End Runner

Run all deterministic steps in sequence:

1. validate/orchestrate Agent 1 + Agent 2 contracts
2. build `geometry_resolver_input.json`
3. resolve `resolved_drawing_instructions.json`
4. render final DXF

```bash
python3 -m adu_drafter.run_pipeline \
  --agent-1-input data/orchestrator_smoke_v2/agent_1_input.json \
  --agent-1-output data/orchestrator_smoke_v2/agent_1_output.json \
  --agent-2-output data/orchestrator_smoke_v2/agent_2_output.json \
  --template data/template.dxf \
  --resolver-input-output data/end_to_end/geometry_resolver_input.json \
  --resolved-instructions-output data/end_to_end/resolved_drawing_instructions.json \
  --output-dxf data/end_to_end/generated_adu.dxf \
  --floorplan-origin-x 100 \
  --floorplan-origin-y 0
```

## Batch Evaluation Harness

Run a tiered corpus and produce telemetry reports:

```bash
python3 scripts/run_evals.py \
  --corpus data/eval_corpus.json \
  --output-dir data/eval_reports/latest \
  --template data/template.dxf \
  --max-attempts 3
```

Outputs:

- `data/eval_reports/latest/eval_report.json`
- `data/eval_reports/latest/eval_report.csv`
- per-case attempt artifacts in `data/eval_reports/latest/cases/`

Example telemetry from sample corpus:

- first-pass success rate
- post-retry success rate
- true-negative conflict rate
- hard failure rate
- average retries per success
- top failure nodes (bounds/overlap/snap/host-wall/schema)

## Agent 2 Candidate Prompt Builder (Semantic Jitter)

Generate deterministic Agent 2 prompt payloads that force spatially distinct
candidate layouts before Best-of-N selection.

The helper emits five variants using anchor constraints:

1. bedroom touches north wall
2. bedroom touches south wall
3. bedroom touches east wall
4. bedroom touches west wall
5. open_living_kitchen occupies southern half of footprint

```bash
python3 scripts/build_agent2_candidate_prompts.py \
  --agent-2-input generated_adu_bestofn_test_input.json \
  --output-dir data/agent2_candidate_prompts
```

Outputs:

- `data/agent2_candidate_prompts/agent2_candidate_prompt_1_north_bedroom.json`
- `data/agent2_candidate_prompts/agent2_candidate_prompt_2_south_bedroom.json`
- `data/agent2_candidate_prompts/agent2_candidate_prompt_3_east_bedroom.json`
- `data/agent2_candidate_prompts/agent2_candidate_prompt_4_west_bedroom.json`
- `data/agent2_candidate_prompts/agent2_candidate_prompt_5_south_living_half.json`

Each payload includes:

- `llm_sampling` (`temperature=0.7`, `top_p=0.9`)
- `semantic_jitter.anchor_directive`
- `agent2_input` (validated canonical input contract)

Use these payloads in your upstream LLM runner to produce diverse
`agent_2_output` candidates for Best-of-N orchestration.

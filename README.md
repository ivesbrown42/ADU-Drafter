# ADU-Drafter

2D-only Proof of Concept pipeline for generating a LA ADU floor plan DXF.

## Architecture

This repository enforces strict decoupling:

- **Reasoning layer (LLM):** outputs only structured JSON (`ADUDesignBrief`).
- **Execution layer (Python):** deterministically validates geometry and drafts DXF.

No 3D or Z-axis logic is used in this phase.

## Project Structure

- `adu_drafter/models.py` – Pydantic schemas for inputs/contracts.
- `adu_drafter/geometry_engine.py` – Shapely buildable-area and QA checks.
- `adu_drafter/drafter.py` – ezdxf drafting engine using `template.dxf`.
- `adu_drafter/main.py` – pipeline entrypoint and LLM integration seam.
- `data/site_input.json` – hardcoded site + setback input.
- `data/manual_design_brief.json` – deterministic design brief sample.

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

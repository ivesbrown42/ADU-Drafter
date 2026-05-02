#!/usr/bin/env bash
# run_agent2_live.sh
# One-command end-to-end pipeline with a LIVE LLM call for Agent 2.
#
# Usage:
#   chmod +x scripts/run_agent2_live.sh
#   ./scripts/run_agent2_live.sh
#
# Prerequisites:
#   1. Copy .env.example to .env and set OPENAI_API_KEY
#   2. pip install -r requirements.txt

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)"
cd "$PROJECT_ROOT"

AGENT1_INPUT="data/eval_cases/case_happy/agent_1_input.json"
AGENT1_OUTPUT="data/eval_cases/case_happy/agent_1_output.json"
AGENT2_INPUT="data/agent_2_input_live.json"
AGENT2_OUTPUT="data/agent_2_output_live.json"
RESOLVER_INPUT="data/geometry_resolver_input_live.json"
RESOLVED="data/resolved_drawing_instructions_live.json"
OUTPUT_DXF="data/generated_adu_live.dxf"

echo "=== Step 1: Build Agent 2 input from Agent 1 artifacts ==="
python - <<'PYEOF'
import json, sys
sys.path.insert(0, ".")
from pathlib import Path
from adu_drafter.contracts import (
    load_agent_1_input, load_agent_1_output, build_agent_2_input
)
a1i = load_agent_1_input(Path("data/eval_cases/case_happy/agent_1_input.json"))
a1o = load_agent_1_output(Path("data/eval_cases/case_happy/agent_1_output.json"))
a2i = build_agent_2_input(a1i, a1o)
out = Path("data/agent_2_input_live.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(a2i.model_dump(mode="json"), indent=2))
print(f"Agent 2 input written to {out}")
PYEOF

echo ""
echo "=== Step 2: Call LLM (Agent 2) ==="
python scripts/call_agent2.py \
    --agent-2-input "$AGENT2_INPUT" \
    --output        "$AGENT2_OUTPUT"

echo ""
echo "=== Step 3: Run deterministic pipeline (orchestrate → resolve → DXF) ==="
python -m adu_drafter.run_pipeline \
    --agent-1-input  "$AGENT1_INPUT" \
    --agent-1-output "$AGENT1_OUTPUT" \
    --agent-2-output "$AGENT2_OUTPUT" \
    --resolver-input-output "$RESOLVER_INPUT" \
    --resolved-instructions-output "$RESOLVED" \
    --output-dxf     "$OUTPUT_DXF" \
    --template       data/template.dxf

echo ""
echo "=== Done! ==="
echo "DXF written to: $OUTPUT_DXF"

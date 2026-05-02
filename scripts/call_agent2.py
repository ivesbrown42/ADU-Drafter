"""Live LLM caller for Agent 2 (ADU floor-plan designer).

Reads a pre-built agent_2_input.json (produced by the orchestrator),
calls the OpenAI Chat Completions API with the Agent 2 system prompt,
and writes the validated response to agent_2_output.json.

Provider is OpenAI by default but can be swapped to any OpenAI-compatible
endpoint (Anthropic via proxy, Ollama, Gemini OpenAI-compat, etc.) by
setting LLM_BASE_URL and LLM_MODEL in your .env or environment.

Usage:
    python scripts/call_agent2.py \\
        --agent-2-input  data/agent_2_input.json \\
        --output         data/agent_2_output.json \\
        --anchor-directive "ANCHOR CONSTRAINT A: bedroom MUST share top edge with NORTH wall."

Environment variables (set in .env or shell):
    OPENAI_API_KEY   required   Your OpenAI API key (or compatible provider key)
    LLM_MODEL        optional   Model name (default: gpt-4o)
    LLM_BASE_URL     optional   Base URL for OpenAI-compatible endpoints
                                e.g. http://localhost:11434/v1  (Ollama)
                                     https://api.anthropic.com/v1  (Anthropic compat)
    LLM_TEMPERATURE  optional   Sampling temperature (default: 0.7)
    LLM_MAX_TOKENS   optional   Max response tokens (default: 4096)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_env() -> None:
    """Load .env file from project root if present (no python-dotenv dependency)."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _build_user_message(agent_2_input: dict, anchor_directive: str | None) -> str:
    """Compose the user message: optional anchor directive + input payload."""
    parts: list[str] = []
    if anchor_directive:
        parts.append(anchor_directive.strip())
        parts.append("")
    parts.append(json.dumps(agent_2_input, indent=2))
    return "\n".join(parts)


def call_agent2(
    agent_2_input: dict,
    *,
    system_prompt: str,
    anchor_directive: str | None = None,
    model: str = "gpt-4o",
    base_url: str | None = None,
    api_key: str,
    temperature: float = 0.7,
    max_tokens: int = 4096,
) -> dict:
    """Call the LLM and return the parsed Agent 2 JSON response.

    Raises ValueError if the response cannot be parsed as JSON or if the
    model returns an obvious refusal.
    """
    try:
        from openai import OpenAI  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "openai package is not installed. Run: pip install openai"
        ) from exc

    client_kwargs: dict = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url

    client = OpenAI(**client_kwargs)

    user_message = _build_user_message(agent_2_input, anchor_directive)

    print(f"[call_agent2] Calling model={model} temperature={temperature} ...")
    response = client.chat.completions.create(
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    raw = response.choices[0].message.content
    if not raw:
        raise ValueError("LLM returned an empty response.")

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"LLM response is not valid JSON: {exc}\nRaw:\n{raw[:500]}") from exc

    print(
        f"[call_agent2] Response received. "
        f"conflict_flag={parsed.get('conflict_flag', '?')} "
        f"rooms={len(parsed.get('rooms', []))}"
    )
    return parsed


def run(
    agent_2_input_path: Path,
    output_path: Path,
    *,
    anchor_directive: str | None = None,
    validate: bool = True,
) -> dict:
    """High-level entry point: load input, call LLM, validate, write output."""
    _load_env()

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise EnvironmentError(
            "OPENAI_API_KEY is not set. "
            "Add it to your .env file or export it in your shell.\n"
            "To use a different provider, set LLM_BASE_URL and LLM_MODEL as well."
        )

    model = os.environ.get("LLM_MODEL", "gpt-4o")
    base_url = os.environ.get("LLM_BASE_URL") or None
    temperature = float(os.environ.get("LLM_TEMPERATURE", "0.7"))
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", "4096"))

    system_prompt_path = PROJECT_ROOT / "prompts" / "agent-2-adu-designer.md"
    if not system_prompt_path.exists():
        raise FileNotFoundError(
            f"Agent 2 system prompt not found at {system_prompt_path}"
        )
    system_prompt = system_prompt_path.read_text(encoding="utf-8")

    agent_2_input = json.loads(agent_2_input_path.read_text(encoding="utf-8"))

    result = call_agent2(
        agent_2_input,
        system_prompt=system_prompt,
        anchor_directive=anchor_directive,
        model=model,
        base_url=base_url,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    if validate:
        from adu_drafter.contracts import load_agent_2_output  # type: ignore
        try:
            load_agent_2_output_from_dict(result)
        except Exception as exc:
            raise ValueError(
                f"LLM output failed contract validation: {exc}\n"
                f"Raw output saved to {output_path} for inspection."
            ) from exc

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[call_agent2] Written to {output_path}")
    return result


def load_agent_2_output_from_dict(data: dict):
    """Validate a dict against the Agent2Output contract."""
    import tempfile, json as _json
    from adu_drafter.contracts import load_agent_2_output
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    ) as f:
        _json.dump(data, f)
        tmp = Path(f.name)
    try:
        return load_agent_2_output(tmp)
    finally:
        tmp.unlink(missing_ok=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Call the LLM to generate an Agent 2 floor-plan output JSON."
    )
    parser.add_argument(
        "--agent-2-input",
        type=Path,
        required=True,
        help="Path to agent_2_input.json produced by the orchestrator.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/agent_2_output.json"),
        help="Path to write the validated agent_2_output.json.",
    )
    parser.add_argument(
        "--anchor-directive",
        type=str,
        default=None,
        help=(
            "Optional spatial anchor constraint injected at the top of the user "
            "message to force geometric diversity. Example: "
            "'ANCHOR CONSTRAINT A: bedroom MUST share top edge with NORTH wall.'"
        ),
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        default=False,
        help="Skip contract validation of LLM output (useful for debugging raw responses).",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        run(
            agent_2_input_path=args.agent_2_input,
            output_path=args.output,
            anchor_directive=args.anchor_directive,
            validate=not args.no_validate,
        )
    except Exception as exc:  # pylint: disable=broad-except
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

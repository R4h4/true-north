"""Model smoke test: one question + one function-tool round-trip.

Run from repo root:  uv run python harness/scripts/smoke_model.py
Reads harness/.env if present. Passes when the model answers AND the tool was
actually invoked (proves the Responses function-calling loop works on the
configured backend).
"""

import pathlib
import sys

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")

from strands import Agent, tool  # noqa: E402  (env must load before strands config)

from agent.model import build_model  # noqa: E402
from agent.tracing import init_tracing  # noqa: E402

calls: list[int] = []


@tool
def get_magic_number() -> int:
    """Return the demo magic number."""
    calls.append(1)
    return 7411


def main() -> int:
    traced = init_tracing()
    agent = Agent(
        model=build_model(),
        tools=[get_magic_number],
        system_prompt="You are a smoke test. Use tools when asked.",
    )
    result = agent("Call get_magic_number and tell me the number it returned.")
    text = str(result)
    print(f"\n--- answer: {text.strip()[:200]}")
    print(f"--- tool invoked: {bool(calls)} | langfuse tracing: {traced}")
    if not calls or "7411" not in text:
        print("SMOKE FAIL: tool round-trip did not happen or number missing")
        return 1
    print("SMOKE PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""DoD-1 core smoke (no UI): Binh asks about retention by channel.

Expected agentic behavior: resolve_term -> ambiguity -> ask_user (we auto-pick
repeat purchase) -> get_metric_context -> query_warehouse -> narrated answer
with % formatting and the caveat named.

Run from repo root:  uv run python harness/scripts/smoke_dod1.py
"""

import pathlib
import sys

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")

from agent.governed_agent import build_agent, run_turn  # noqa: E402
from agent.tracing import init_tracing  # noqa: E402

TOKEN = "tok-analyst-binh"

asked: list[str] = []


def auto_answer(question: str, options: list[str]) -> str:
    asked.append(question)
    print(f"\n[ask_user] {question}\n  options: {options}")
    choice = next((o for o in options if "repeat" in o.lower()), options[0] if options else "repeat purchase")
    print(f"  -> auto-answer: {choice}")
    return choice


def main() -> int:
    init_tracing()
    agent = build_agent()
    result = run_turn(agent, TOKEN, auto_answer, "How is our customer retention doing by channel?")
    text = str(result)
    if "query_warehouse" not in str(agent.messages) and text.strip().endswith("?"):
        # Agent asked a conversational follow-up; answer like a user would.
        result = run_turn(agent, TOKEN, auto_answer, "No specific period - use all available data.")
        text = str(result)

    tool_uses = [
        (block["toolUse"]["name"], block["toolUse"].get("input"))
        for msg in agent.messages
        for block in (msg.get("content") or [])
        if isinstance(block, dict) and "toolUse" in block
    ]
    tool_names = [name for name, _ in tool_uses]
    print("\n--- tool sequence:")
    for name, tool_input in tool_uses:
        print(f"    {name}({tool_input})")
    print(f"--- answer:\n{text.strip()[:1200]}")

    checks = {
        "resolved term via KG": "resolve_term" in tool_names,
        "asked the user (no guessing)": bool(asked),
        "loaded metric context": "get_metric_context" in tool_names,
        "queried warehouse": "query_warehouse" in tool_names,
        "percent formatting in answer": "%" in text,
    }
    failed = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    print("DOD1 CORE SMOKE " + ("PASS" if not failed else f"FAIL ({failed})"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

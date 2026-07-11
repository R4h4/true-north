"""AG-UI server: exposes the governed agent to the CopilotKit frontend.

Run from repo root:  uv run uvicorn agent.server:app --app-dir harness --port 8000

Design decisions (phase-3 plan + code review):
- Persona rides in AG-UI forwarded_props (fallback: shared state); the token
  binds per run() call in THIS task's context - never at agent build time -
  so concurrent sessions cannot leak personas.
- ask_user is a FRONTEND action (CopilotKit renderAndWaitForResponse); the
  adapter syncs frontend tools into the agent per thread, so the local Python
  ask_user tool is excluded here.
- KG shared state: state_from_result hooks on the three KG tools merge each
  envelope into a per-thread subgraph, emitted as AG-UI state for the side
  panel.
- Open access with guards: MAX_TURNS_PER_SESSION per thread and a global
  DAILY_TOKEN_BUDGET-ish turn budget (token counting arrives with Langfuse;
  turns are the cheap proxy until then).
"""

import os
import pathlib
import time
from typing import Any, AsyncIterator

from dotenv import load_dotenv

load_dotenv(pathlib.Path(__file__).resolve().parents[1] / ".env")

from ag_ui.core import (  # noqa: E402
    EventType,
    ReasoningMessageContentEvent,
    ReasoningMessageEndEvent,
    RunAgentInput,
    StateSnapshotEvent,
)
from ag_ui_strands import (  # noqa: E402
    StrandsAgent,
    StrandsAgentConfig,
    ToolBehavior,
    create_strands_app,
)

from agent.governed_agent import build_agent  # noqa: E402
from agent.kg_context import empty_graph, merge_envelope  # noqa: E402
from agent.tools import current_dataset, current_token, reset_run_cache  # noqa: E402
from agent.tracing import init_tracing  # noqa: E402

# Persona ids are unique ACROSS tenants, so the frontend only sends a persona
# and the dataset rides along here (tn --dataset is a global option; tokens
# come from each tenant's users.yaml).
PERSONAS = {
    # Phong Vũ retail
    "mai": {"token": "tok-exec-mai", "dataset": "retail"},
    "duc": {"token": "tok-rm-south-duc", "dataset": "retail"},
    "lan": {"token": "tok-mkt-lan", "dataset": "retail"},
    "binh": {"token": "tok-analyst-binh", "dataset": "retail"},
    # Shinhan Finance consumer lending
    "sujin": {"token": "tok-exec-sujin", "dataset": "shinhan"},
    "minh": {"token": "tok-risk-minh", "dataset": "shinhan"},
    "thao": {"token": "tok-coll-thao", "dataset": "shinhan"},
    "long": {"token": "tok-partner-long", "dataset": "shinhan"},
}
DEFAULT_PERSONA = "binh"

_graphs_by_thread: dict[str, dict] = {}
_turns_by_thread: dict[str, int] = {}
_thinking_by_thread: dict[str, str] = {}


def _shared_state(thread_id: str) -> dict:
    """Full shared-state payload. AG-UI STATE_SNAPSHOT replaces the whole
    state object, so every emitter must carry every key or it wipes the rest."""
    return {
        "kg_context": _graphs_by_thread.get(thread_id) or empty_graph(),
        "thinking": _thinking_by_thread.get(thread_id, ""),
    }


def _kg_state(ctx) -> dict | None:
    """state_from_result hook: merge the tool's envelope into this thread's graph."""
    thread_id = ctx.input_data.thread_id or "default"
    graph = _graphs_by_thread.setdefault(thread_id, empty_graph())
    merge_envelope(graph, ctx.result_data)
    return _shared_state(thread_id)


class GovernedStrandsAgent(StrandsAgent):
    """Binds persona token + fresh run cache per run, in the run's own context."""

    async def run(self, input_data: RunAgentInput) -> AsyncIterator[Any]:
        persona = (
            (input_data.forwarded_props or {}).get("persona")
            or (input_data.state or {}).get("persona")
            or DEFAULT_PERSONA
        )
        persona_cfg = PERSONAS.get(str(persona).lower())
        thread_id = input_data.thread_id or "default"

        max_turns = int(os.getenv("MAX_TURNS_PER_SESSION", "20"))
        _turns_by_thread[thread_id] = _turns_by_thread.get(thread_id, 0) + 1

        if persona_cfg is None or _turns_by_thread[thread_id] > max_turns:
            # Emit a normal run with a text explanation instead of crashing the UI.
            reason = (
                f"Unknown persona {persona!r}." if persona_cfg is None
                else "This demo session reached its turn limit - start a new chat."
            )
            async for event in self._refusal_run(input_data, reason):
                yield event
            return

        current_token.set(persona_cfg["token"])
        current_dataset.set(persona_cfg["dataset"])
        reset_run_cache()

        # CopilotKit's chat UI drops AG-UI Reasoning events, so mirror the
        # model's reasoning summaries into shared state (same channel as the
        # KG panel). Throttled: one snapshot per ~0.3s, plus a final flush.
        _thinking_by_thread[thread_id] = ""
        last_emit = 0.0
        cleared = False

        def _snapshot() -> StateSnapshotEvent:
            return StateSnapshotEvent(
                type=EventType.STATE_SNAPSHOT, snapshot=_shared_state(thread_id)
            )

        async for event in super().run(input_data):
            if isinstance(event, StateSnapshotEvent):
                # The base class emits snapshots from its own state store
                # (tool-behavior results + a terminal flush) that don't know
                # about `thinking` - and a snapshot REPLACES client state, so
                # a missing key erases the reasoning mid-conversation.
                merged = dict(event.snapshot or {})
                merged["thinking"] = _thinking_by_thread.get(thread_id, "")
                merged.setdefault(
                    "kg_context", _graphs_by_thread.get(thread_id) or empty_graph()
                )
                event = StateSnapshotEvent(
                    type=EventType.STATE_SNAPSHOT, snapshot=merged
                )
            yield event
            if not cleared:
                # First event was RUN_STARTED: clear the previous turn's text.
                cleared = True
                yield _snapshot()
            if isinstance(event, ReasoningMessageContentEvent):
                _thinking_by_thread[thread_id] += event.delta
                if time.monotonic() - last_emit > 0.3:
                    last_emit = time.monotonic()
                    yield _snapshot()
            elif isinstance(event, ReasoningMessageEndEvent):
                _thinking_by_thread[thread_id] += "\n\n"
                yield _snapshot()

    async def _refusal_run(self, input_data: RunAgentInput, reason: str):
        from ag_ui.core import (
            EventType,
            RunFinishedEvent,
            RunStartedEvent,
            TextMessageContentEvent,
            TextMessageEndEvent,
            TextMessageStartEvent,
        )
        import uuid

        message_id = str(uuid.uuid4())
        yield RunStartedEvent(type=EventType.RUN_STARTED, thread_id=input_data.thread_id, run_id=input_data.run_id)
        yield TextMessageStartEvent(type=EventType.TEXT_MESSAGE_START, message_id=message_id, role="assistant")
        yield TextMessageContentEvent(type=EventType.TEXT_MESSAGE_CONTENT, message_id=message_id, delta=reason)
        yield TextMessageEndEvent(type=EventType.TEXT_MESSAGE_END, message_id=message_id)
        yield RunFinishedEvent(type=EventType.RUN_FINISHED, thread_id=input_data.thread_id, run_id=input_data.run_id)


init_tracing()

_kg_behavior = ToolBehavior(state_from_result=_kg_state)
agui_agent = GovernedStrandsAgent(
    agent=build_agent(include_local_ask_user=False),
    name="true-north",
    description="Governed BI analyst over the tenant's governed warehouse",
    config=StrandsAgentConfig(
        tool_behaviors={
            "resolve_term": _kg_behavior,
            "get_metric_context": _kg_behavior,
            "check_metric_access": _kg_behavior,
            # describe carries access.allowed - denied metrics render locked
            "describe_metric": _kg_behavior,
        }
    ),
)

app = create_strands_app(agui_agent, path="/")

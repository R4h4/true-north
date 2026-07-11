"""Agent assembly: model + governed tools + ask_user bridge.

ask_user is UI-pluggable: the AG-UI server binds it to a human-in-the-loop
interrupt; smoke scripts bind an auto-responder. It is a ContextVar so
concurrent sessions can't cross wires.
"""

from contextvars import ContextVar
from typing import Callable

from strands import Agent, tool

from agent.charts import render_chart
from agent.model import build_model
from agent.system_prompt import build_system_prompt
from agent.tools import GOVERNED_TOOLS, current_token, kg_schema, reset_run_cache

AskUserFn = Callable[[str, list[str]], str]
ask_user_handler: ContextVar[AskUserFn] = ContextVar("ask_user_handler")


@tool
def ask_user(question: str, options: list[str]) -> str:
    """Pause and ask the user to choose - REQUIRED for ambiguous terms (metric
    variants) and METRIC_NOT_FOUND candidates. Returns the user's choice."""
    return ask_user_handler.get()(question, options)


def build_agent(include_local_ask_user: bool = True) -> Agent:
    """Build a persona-agnostic agent. The persona token binds per turn via
    run_turn - never at build time, so a cached agent can't leak personas
    across concurrent sessions.

    include_local_ask_user=False for the AG-UI server: there the frontend
    registers ask_user as a CopilotKit action and the adapter proxies it to
    the model, pausing in the browser instead of in Python.
    """
    schema = kg_schema()
    if not schema.get("ok"):
        raise RuntimeError(f"tn kg schema failed at bootstrap: {schema.get('error')}")
    tools = GOVERNED_TOOLS + [render_chart] + ([ask_user] if include_local_ask_user else [])
    return Agent(
        model=build_model(),
        tools=tools,
        system_prompt=build_system_prompt(schema),
    )


def run_turn(agent: Agent, token: str, ask_handler: AskUserFn, message: str):
    """Run one user turn with token/ask-handler/cache bound in THIS context.

    Strands copies the current context into its worker tasks at invocation
    time, so binding here (immediately before the call) is what makes the
    ContextVars reach the tools - and a fresh cache per turn keeps the
    idempotency guard scoped to a single turn.
    """
    current_token.set(token)
    ask_user_handler.set(ask_handler)
    reset_run_cache()
    return agent(message)

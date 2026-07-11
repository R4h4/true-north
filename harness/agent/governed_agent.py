"""Agent assembly: model + governed tools + ask_user bridge.

ask_user is UI-pluggable: the AG-UI server binds it to a human-in-the-loop
interrupt; smoke scripts bind an auto-responder. It is a ContextVar so
concurrent sessions can't cross wires.
"""

from contextvars import ContextVar
from typing import Callable

from strands import Agent, tool

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


def build_agent(token: str) -> Agent:
    current_token.set(token)
    reset_run_cache()
    return Agent(
        model=build_model(),
        tools=GOVERNED_TOOLS + [ask_user],
        system_prompt=build_system_prompt(kg_schema()),
    )

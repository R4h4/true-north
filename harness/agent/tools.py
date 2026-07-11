"""Typed governed tools for the Strands agent.

The model never writes Cypher or SQL. KG tools render the canonical Cypher
from CONTRACT.md §4.4 harness-side (byte-exact with the replay fixtures in
docs/USING-TN.md), so every stub call is fixture-exact by construction and
identical against the real graph later.

The persona token is a ContextVar set per session/run by the caller
(server, smoke script) - tools never take it as a model-visible argument.
"""

import re
from contextvars import ContextVar
from typing import Any

from strands import tool

from agent.tn_client import run_tn

current_token: ContextVar[str] = ContextVar("tn_token")
# Per-run idempotency cache: identical (args) tuples are served from cache so
# the agent can never hammer the CLI with a repeated failing call.
_run_cache: ContextVar[dict] = ContextVar("tn_run_cache")


def reset_run_cache() -> None:
    _run_cache.set({})

# Canonical Cypher (CONTRACT §4.4). Whitespace and quoting must stay byte-exact:
# the stub replays on exact match.
_RESOLVE_TERM = (
    "MATCH (c:Concept) WHERE c.name =~ '{rx}' "
    "OR any(a IN c.aliases WHERE a =~ '{rx}') "
    "OPTIONAL MATCH (c)<-[:VARIANT_OF]-(v:Concept)-[:MEASURED_BY]->(m:Metric) "
    "RETURN c, v, m"
)
_METRIC_DETAIL = (
    "MATCH (m:Metric {{key: '{key}'}}) "
    "OPTIONAL MATCH (m)-[:HAS_DIMENSION]->(d:Dimension) "
    "OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) "
    "OPTIONAL MATCH (m)-[:COMPUTED_FROM]->(t:Table) "
    "RETURN m, collect(DISTINCT d) AS dims, collect(DISTINCT k) AS caveats, "
    "collect(DISTINCT t) AS tables"
)
_ACCESS_CHECK = (
    "MATCH (m:Metric) WHERE m.key IN [{keys}] "
    "OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) "
    "RETURN m, collect(k) AS caveats"
)


def _with_token(args: list[str]) -> dict[str, Any]:
    token = current_token.get()
    try:
        cache = _run_cache.get()
    except LookupError:
        # Tool context was copied from the caller: a set() here would be
        # discarded on return, so this fallback dict is per-call only. Callers
        # must go through run_turn, which seeds the cache in the outer context.
        cache = {}
    key = (token, *args)
    if key in cache:
        cached = dict(cache[key])
        cached["_note"] = (
            "You already made this exact call this turn; result repeated. "
            "Do not call again - act on it or tell the user."
        )
        return cached
    envelope = run_tn(args + ["--token", token])
    cache[key] = envelope
    return envelope


_TERM_RE = re.compile(r"^[a-z0-9_| ]+$", re.IGNORECASE)
_KEY_RE = re.compile(r"^[a-z0-9_]+$")


def resolve_term_cypher(term: str) -> str:
    """Render the canonical term-resolution regex; '|' alternatives get parens."""
    if not _TERM_RE.match(term):
        raise ValueError(f"term must be alphanumeric words or '|' alternatives, got {term!r}")
    rx = f"(?i).*({term}).*" if "|" in term else f"(?i).*{term}.*"
    return _RESOLVE_TERM.format(rx=rx)


def metric_detail_cypher(metric_key: str) -> str:
    """Render the canonical metric-detail query (single source for gate + tool)."""
    if not _KEY_RE.match(metric_key):
        raise ValueError(f"metric_key must be snake_case, got {metric_key!r}")
    return _METRIC_DETAIL.format(key=metric_key)


def access_check_cypher(metric_keys: list[str]) -> str:
    """Render the canonical access-annotation query (no space in join: fixture-exact)."""
    for key in metric_keys:
        if not _KEY_RE.match(key):
            raise ValueError(f"metric_key must be snake_case, got {key!r}")
    return _ACCESS_CHECK.format(keys=",".join(f"'{k}'" for k in metric_keys))


def _is_no_fixture(envelope: dict) -> bool:
    err = envelope.get("error") or {}
    return err.get("code") == "INTERNAL" and "fixture" in (err.get("message") or "")


@tool
def resolve_term(term: str) -> dict:
    """Resolve a business term in the knowledge graph. Pass the SINGLE most
    distinctive word ('retention', 'basket', 'margin') or '|'-alternatives
    ('revenue|gmv') - never a full phrase. Returns matching Concepts, their
    variants, and the Metrics measuring them. A parent Concept WITHOUT a
    measuring Metric means the term is ambiguous: ask the user which variant
    they mean - never guess."""
    envelope = _with_token(["kg", "query", resolve_term_cypher(term)])
    if _is_no_fixture(envelope) and " " in term:
        # Multi-word phrase missed the fixtures/graph: fall back to each
        # distinctive word so 'customer retention' still resolves 'retention'.
        for word in sorted(term.split(), key=len, reverse=True):
            if len(word) <= 3:
                continue
            envelope = _with_token(["kg", "query", resolve_term_cypher(word)])
            if not _is_no_fixture(envelope):
                break
    return envelope


@tool
def get_metric_context(metric_key: str) -> dict:
    """Load a metric's governed context before querying it: valid dimensions,
    caveats (constraints you must narrate), and source tables."""
    return _with_token(["kg", "query", metric_detail_cypher(metric_key)])


@tool
def check_metric_access(metric_keys: list[str]) -> dict:
    """Check access annotations (_access.readable) and caveats for specific
    metric keys - use when a metric may exist but be denied for this user."""
    return _with_token(["kg", "query", access_check_cypher(metric_keys)])


@tool
def list_metrics() -> dict:
    """List every governed metric visible to the current user."""
    return _with_token(["metrics", "list"])


@tool
def describe_metric(metric_key: str) -> dict:
    """Describe one metric: definition, dimensions, and whether the current
    user can compute it (denied metrics stay visible with a reason)."""
    return _with_token(["metrics", "describe", metric_key])


@tool
def query_warehouse(
    metric: str,
    group_by: str | None = None,
    time_grain: str | None = None,
    filter: str | None = None,
    start: str | None = None,
    end: str | None = None,
) -> dict:
    """Run a governed data query for one metric key (exact key from the KG -
    never guessed). OMIT every parameter you don't need - never pass empty
    strings or defaults. group_by/filter use dimension KEYS exactly as returned
    by get_metric_context (e.g. 'channel'), NEVER display names ('Sales
    channel'). time_grain is a TIME granularity only (e.g. 'month') and is NOT
    for dimensions - leave it out unless the user asks for a time series.
    Dates are YYYY-MM-DD; filter syntax: "dimension = 'value'". The envelope's
    metadata.applied_permissions, warnings, and provenance are part of the
    answer - narrate them."""
    args = ["query", "--metric", metric]
    for flag, value in (
        ("--group-by", group_by),
        ("--grain", time_grain),
        ("--filter", filter),
        ("--start", start),
        ("--end", end),
    ):
        # Models sometimes send "" for unused params; empty flags are never
        # intended, so only forward real values.
        if value and value.strip():
            args += [flag, value]
    envelope = _with_token(args)
    if envelope.get("ok"):
        # Stash for render_chart: mutating the cache dict (not set()) is what
        # survives the per-tool context copy.
        try:
            _run_cache.get()["__last_query__"] = envelope
        except LookupError:
            pass
    return envelope


def kg_schema() -> dict:
    """Bootstrap call (no token needed): labels, invariants, canonical Cypher."""
    return run_tn(["kg", "schema"])


@tool
def get_kg_schema() -> dict:
    """Call this FIRST in every new conversation, before any other tool: it
    returns the knowledge graph's node labels, relationship types, and
    invariants - the map of what can be resolved and queried. You do not know
    the graph shape until you call it."""
    try:
        cache = _run_cache.get()
    except LookupError:
        cache = {}
    if "__kg_schema__" in cache:
        cached = dict(cache["__kg_schema__"])
        cached["_note"] = "schema already loaded this turn - do not call again"
        return cached
    envelope = kg_schema()
    cache["__kg_schema__"] = envelope
    return envelope


GOVERNED_TOOLS = [
    get_kg_schema,
    resolve_term,
    get_metric_context,
    check_metric_access,
    list_metrics,
    describe_metric,
    query_warehouse,
]

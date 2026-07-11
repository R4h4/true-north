---
phase: 3
title: "Harness Agent: Strands + Chainlit on GPT-5.5, Langfuse, Charts"
status: pending
priority: P1
dependencies: [2]
---

# Phase 3: Harness Agent: Strands + Chainlit on GPT-5.5, Langfuse, Charts

## Overview

Phong's main build — and per Phong's directive (2026-07-11): the harness must be
**visibly agentic** (thoughts, plan, tool selection, where knowledge is retrieved from,
follow-up questions with the user in a loop until context suffices → insight report),
and we **adopt an existing harness instead of building one** due to the time limit.
Chosen stack (research report
`researcher-260711-1718-GH-3-agentic-harness-framework-report.md`):

- **Strands Agents SDK** (AWS OSS, 1.x) owns the agent loop: `@tool` functions,
  `stream_async` emitting reasoning/text/tool events, first-party Langfuse OTel export.
- **Chainlit** owns the UI: native step tree for thoughts/tool calls,
  `cl.AskUserMessage` for mid-run follow-up questions, `cl.Plotly` for charts, and a
  **live KG-context sidebar** (`cl.ElementSidebar`) showing the subgraph the agent has
  explored so far. **No auth** — open access by Phong's decision (2026-07-11): anyone
  with the demo URL can try it.
- Model: **GPT-5.5 via bedrock-mantle** (OpenAI-compatible endpoint), configured as
  Strands' OpenAI provider with a custom base_url.

Developed 100% against Karsten's replay stub (PR #4: `uv run tn`, fixtures in
`governance/fixtures/replay/`, agent guide at `docs/USING-TN.md`).

## Requirements

- Functional: agent implements the **intended loop from USING-TN.md** (kg schema
  bootstrap → term resolve → variant disambiguation **by asking the user via
  `cl.AskUserMessage`** → metric detail → data query → envelope-driven narration);
  persona token on every CLI call; **every reasoning/tool step visible in the UI as a
  Chainlit step**; **KG-context sidebar that grows as the agent explores** (each
  `query_knowledge_graph` result adds its nodes/edges to a session subgraph rendered
  beside the chat — the user watches context build up); Plotly chart rendering from
  query results; pin-to-dashboard; md/xlsx/parquet exports.
- Non-functional: every user turn = one Langfuse trace (via Strands OTel) with nested
  generation + tool spans, session + persona tagged; model/CLI/keys all env-configured;
  loop capped by Strands' max-iterations config with a graceful "couldn't answer" path.

## Architecture

```
Chainlit chat (@cl.on_message) ── Strands Agent.stream_async(question)   harness/agent/
  │  session/persona tags via OTel baggage (StrandsTelemetry → Langfuse /api/public/otel)
  ├─ model = OpenAIModel(client_args={base_url: $OPENAI_BASE_URL,   # bedrock-mantle
  │                                    api_key:  $OPENAI_API_KEY},  # Bedrock API key
  │                       model_id=$MODEL_ID)                       # openai.gpt-5.5 — verify day 0
  ├─ event stream → UI mapping:
  │     reasoning events  → cl.Step(type="llm")   (the visible "thoughts/plan")
  │     tool-use events   → cl.Step(type="tool")  (name + input + envelope output)
  │     text events       → streamed answer message
  ├─ @tool functions → subprocess: $GOVERNED_CLI_CMD (default `uv run tn`)
  │     tn kg query|metrics list|metrics describe|query --token $TOKEN ...
  │     v0.3 envelope (incl. error.code/details) returned as the tool result
  ├─ ask_user(question, options) tool → cl.AskUserMessage — the follow-up loop
  ├─ every kg-tool envelope → kg_context: session subgraph accumulates nodes/edges,
  │     re-rendered as a Plotly network in cl.ElementSidebar (the "context building up" view)
  └─ render_chart(plotly_spec) → validate via plotly.io.from_json, inject last
        result rows, cl.Plotly element · 📌 pin → persisted to harness/dashboard/
```

- **Strands owns the loop mechanics** (tool dispatch, reasoning-item handling, retries,
  iteration cap) — no hand-rolled Responses-API loop. The OpenAI-provider config and the
  bedrock-mantle API surface (Chat Completions vs Responses) are the day-0 verification
  item (phase 5A); fallback if mismatched: Strands' LiteLLM provider or a custom model
  provider. Second fallback: OpenAI Agents SDK (works with custom base_url; Langfuse via
  OpenInference).
- **Stub-replay constraints (from PR #4 — govern dev-time behavior):**
  - The stub matches requests against fixtures; `tn kg query` matching is effectively
    **exact-Cypher**. The system prompt must instruct: use the canonical queries from
    `tn kg schema` **verbatim**, substituting only the term-regex / metric-key slots.
    Free-styled Cypher works against the real graph later but returns
    `INTERNAL: "no replay fixture"` on the stub.
  - Treat `INTERNAL` + "no replay fixture" as a stub limitation in dev: the agent should
    tell the user it can't answer that on current fixtures (not retry-loop). Missing
    scenarios → fixture-only PRs to `governance/fixtures/replay/` (Karsten merges these
    same-day per phase-2 agreement).
  - Denial precedence (contract clarification in PR #4): table-read blocks →
    `ACCESS_DENIED_TABLE` even for metric queries; `ACCESS_DENIED_METRIC` = masked-column
    denials only.
- **Tracing = Strands OTel → Langfuse**: `strands-agents[otel]` + `StrandsTelemetry`
  pointed at Langfuse's OTel endpoint (documented first-party both sides). Replaces the
  earlier `langfuse.openai` drop-in + manual `@observe` plan. Session id + persona set as
  trace attributes per Langfuse's Strands cookbook. Cost tracking: add `openai.gpt-5.5`
  pricing manually in the Langfuse dashboard.
- Tools map 1:1 onto contract v0.3 commands (CONTRACT.md is the spec, not this plan):
  `query_knowledge_graph(cypher)` → `tn kg query`; `query_warehouse(metric, group_by[],
  grain, filters[], start, end)` → `tn query` flags — the model never writes SQL, the
  `@tool` signature enforces the shape; `list_metrics()` / `describe_metric(key)`
  → `tn metrics list|describe`. At startup, load `tn kg schema` output (labels,
  invariants, canonical Cypher examples) into the system prompt.
- **`ask_user(question, options[])` tool**: bridges Strands → `cl.AskUserMessage` so the
  model can pause and ask (variant disambiguation, candidate selection) instead of
  guessing — this is the "loop until enough context" behavior, and it's a tool call, so
  it appears in the Langfuse trace like any other step.
- **KG-context sidebar** (`harness/agent/kg_context.py`): a per-session dict of
  `{nodes, edges}` keyed by node id. After every `query_knowledge_graph` /
  `describe_metric` call, the harness parses the envelope rows (Concept / Metric /
  Dimension / Table / Constraint nodes, VARIANT_OF / MEASURED_BY / HAS_DIMENSION /
  COMPUTED_FROM / CONSTRAINS edges — the contract §4 shapes) and merges them in.
  Rendered as a Plotly network figure (spring-ish static layout, node color by label,
  **newly added nodes highlighted**, `_access.readable: false` nodes marked
  locked — DoD-3's denied metric shows up visibly locked in the sidebar) via
  `cl.ElementSidebar.set_elements`, title "What the agent knows so far". Pure Python +
  Plotly, no new deps; parse defensively — unknown row shapes are skipped, never crash
  the turn.
- **`render_chart(title, plotly_spec)` tool** (switched from Vega-Lite → Plotly because
  Chainlit renders Plotly natively — see the 1718 research report; same
  validate-and-self-correct pattern): spec arrives WITHOUT data; the harness injects the
  last `tn query` result rows, validates via `plotly.io.from_json`, and returns
  validation errors as the tool result so the model self-corrects — the same retry
  pattern as `METRIC_NOT_FOUND.candidates`. `tn`'s `columns[]: {name, type, unit}` maps
  to axes/format.
- **Dashboard & exports:** 📌 per chart persists `{spec, data, title, persona,
  applied_permissions}` as JSON under `harness/dashboard/`; a minimal read-only viewer
  page lists pins (persona-scoped by construction — Đức's pins are visibly South-only).
  Per-result export files offered in-chat: Markdown report (narrative + caveats +
  `applied_permissions` + `provenance.compiled_sql` appendix), XLSX (BI), Parquet
  (analytics) — pandas one-liners, attached via `cl.File`.
- Self-correction paths are contract features (full table in USING-TN.md):
  `METRIC_NOT_FOUND.candidates` → surface to user (via `ask_user`), don't pick silently;
  `INVALID_DIMENSION_VALUE.did_you_mean` → retry with canonical spelling;
  `INVALID_DIMENSION.valid_dimensions` → regroup — pass `error.details` through in the
  tool result so the model recovers in one turn.
- Answer narration is envelope-driven: `metadata.applied_permissions` (typed objects with
  `display` strings) → "your view is scoped to region South"; `warnings` (`STALE_DATA`,
  `ROW_LIMIT`) → caveats; `provenance.compiled_sql` + `constraint_keys` → show-your-work.
  A `Metric` node with `_access.readable: false` → the "exists but you can't see it" beat.
- System prompt encodes the governed-BI stance and USING-TN.md's intended loop:
  multi-round KG exploration first; parent-Concept-without-MEASURED_BY = `ask_user` which
  variant, never guess; canonical Cypher verbatim; VND/tỷ formatting; ratios arrive
  as 0–1 fractions — percent formatting is the harness's job.

## Related Code Files

- Create: `harness/agent/__init__.py`, `harness/agent/tools.py` (@tool wrappers →
  `GOVERNED_CLI_CMD` subprocess), `harness/agent/model.py` (Strands OpenAI provider →
  bedrock-mantle), `harness/agent/tracing.py` (StrandsTelemetry → Langfuse),
  `harness/agent/system_prompt.py`, `harness/agent/charts.py` (Plotly validation + data
  injection), `harness/agent/exports.py` (md/xlsx/parquet)
- Create: `harness/app.py` (Chainlit: on_message → stream_async → step mapping, ask_user
  bridge, persona picker via chat profiles, KG-sidebar refresh — no auth),
  `harness/agent/kg_context.py` (session subgraph + Plotly network rendering),
  `harness/dashboard/` (pinned-chart JSON + minimal viewer), `harness/.env.example`
  (`MODEL_ID=openai.gpt-5.5`, `OPENAI_BASE_URL` (bedrock-mantle), `OPENAI_API_KEY`
  (Bedrock API key), `GOVERNED_CLI_CMD`, `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL`,
  `MAX_TURNS_PER_SESSION`)
- Modify: `harness/pyproject.toml` (add `strands-agents[otel]`, chainlit, plotly,
  pandas, openpyxl, pyarrow; pin versions)

## Implementation Steps

1. `model.py` + `tracing.py`: Strands agent with OpenAI provider pointed at
   bedrock-mantle; StrandsTelemetry → Langfuse; smoke-test a plain question end-to-end
   and confirm the trace tree lands in Langfuse (needs Phase 5A key). This step also
   settles the Chat-Completions-vs-Responses question.
2. `tools.py`: five `@tool` functions + `ask_user` stub, shelling out to
   `GOVERNED_CLI_CMD`; exit 1 with envelope → tool result carrying `error.code` +
   `error.details`; non-zero without parseable envelope → treat as `INTERNAL` per
   contract.
3. `system_prompt.py`: governed-analyst prompt built from `tn kg schema` output +
   USING-TN.md loop + verbatim-Cypher rule + ask-don't-guess rule + narration rules.
4. `app.py`: Chainlit chat — persona picker (Mai/executive, Đức/regional-manager-South,
   Lan/marketing-ops, Bình/analyst) via chat profiles, `stream_async` → `cl.Step`
   mapping (reasoning + tool steps visible), `ask_user` → `cl.AskUserMessage` bridge;
   no auth (open access); `MAX_TURNS_PER_SESSION` guard against quota burn; new chat =
   new Langfuse session id.
5. `kg_context.py`: envelope → subgraph merge + Plotly network; wire the sidebar
   refresh after each KG/describe tool call; verify on the DoD-1 exploration rounds.
6. `charts.py` + `exports.py`: Plotly validation/injection + `cl.Plotly` rendering;
   pin persistence; md/xlsx/parquet writers attached via `cl.File`.
7. Run the Definition-of-Done script below end-to-end; fix until green.

## Definition of Done — the four demo conversations (all on the stub)

Every scenario below uses only requests fixtured in PR #4 (`docs/USING-TN.md`); each must
work as a live chat **with the agent's reasoning and tool steps visible in the Chainlit
step tree**, and the full trace visible in Langfuse. **Phase 3 is done when all four pass
twice in a row.**

**DoD-1 · Ambiguity + trap caveat (Bình, analyst).**
"How is our customer retention doing by channel?" → agent resolves 'retention' via
canonical KG query → parent Concept with 2 variants (repeat-purchase vs loyalty-activity)
→ agent **asks the user via `ask_user`** which; user picks repeat-purchase → agent loads
metric detail (dims/caveats/tables) → `tn query --metric repeat_purchase_rate_90d
--group-by channel` → answer shows a ratio formatted as %, names the caveat(s), renders a
bar chart via `render_chart`. ✅ when: agent asked instead of guessing; chart rendered
from real result rows; caveat named in prose; KG-exploration steps visible in the UI;
**the sidebar visibly grows across the turn** (Concept → two variants → chosen metric →
its dimensions/tables appear in sequence).

**DoD-2 · Row-level security, side by side (Mai vs Đức).**
Same question, two chats: "Net revenue by channel this year?" as Mai (national), then as
Đức → South-filtered numbers, and the answer explicitly says the view is scoped to region
South (from `applied_permissions.display`). ✅ when: numbers differ between personas; the
row filter is disclosed in Đức's prose unprompted; both traces carry the right `user_id`.

**DoD-3 · Exists-but-denied (Lan, marketing).**
"What's our gross margin by category?" → `ACCESS_DENIED_METRIC` with masked-column
reason → answer says the metric exists but her role can't compute it (names the reason),
optionally shows `metrics describe gross_margin` (denied-but-visible). Follow-up "how
about inventory days?" → `ACCESS_DENIED_TABLE`. ✅ when: no retry loop; both denial
narrations are accurate; agent stays helpful (offers what she CAN see, e.g. net_revenue).

**DoD-4 · Self-correction (Mai).**
"Show me revenue for offline stores" → `--metric revenue` returns
`METRIC_NOT_FOUND` + candidates → agent surfaces candidates (gross vs net) via
`ask_user`, user picks net → `--filter "channel = 'offline'"` returns
`INVALID_DIMENSION_VALUE` + `did_you_mean: in_store` → agent retries with `in_store` and
answers. ✅ when: both recoveries happen (one asks the user, one auto-corrects), visible
as distinct tool steps in the UI and tool spans in the Langfuse trace.

**Plus, on any DoD scenario:** 📌 pin the chart → it appears in the pinned-dashboard view
with persona + permissions; the three export files produce a readable .md, an .xlsx that
opens in Excel/Numbers, and a .parquet that `pandas.read_parquet` round-trips.

## Success Criteria

- [ ] DoD-1…DoD-4 pass twice consecutively on the stub, each as a natural chat.
- [ ] Agentic visibility: reasoning + every tool call rendered as Chainlit steps
  (chain-of-thought mode `tool_call` at minimum; `full` if reasoning summaries stream).
- [ ] KG-context sidebar: grows during DoD-1's exploration rounds; DoD-3 shows Lan's
  denied metric as a locked node; resets on new chat.
- [ ] Langfuse trace tree per turn (via Strands OTel): trace → agent span →
  N×(generation | tool span), session + persona tagged, token usage populated.
- [ ] Chart pipeline: invalid spec from the model self-corrects via validation-error
  round-trip (force once by prompt to verify).
- [ ] Pin + exports work per the DoD rider above.
- [ ] No harness code imports Karsten's Python modules (subprocess + files only).

## Risk Assessment

- **bedrock-mantle API surface mismatch** (most likely blocker): Strands' OpenAI
  provider speaks Chat Completions; if `openai.gpt-5.5` on bedrock-mantle is
  Responses-only, switch to Strands' LiteLLM provider or a custom model provider;
  second fallback: OpenAI Agents SDK. Settled in step 1 / phase 5A — do not proceed past
  step 1 without it.
- **LLM Cypher misses replay fixtures** (exact-match) → verbatim-canonical-queries rule
  in the system prompt; if GPT-5.5 still paraphrases, wrap `query_knowledge_graph` to
  template the two canonical queries harness-side (tool args become `term_regex` /
  `metric_key` instead of raw Cypher) — contract-legal and stub-proof.
- **Chainlit maintenance** (community-maintained since May 2025) → active releases;
  demo-scoped usage of stable primitives (Step, AskUserMessage, Plotly, auth) only.
- **Strands↔Chainlit event mapping friction** (reasoning events shape varies by
  provider) → map defensively: unknown event types collapse into the current step's
  output rather than crashing the stream.
- **Open access burns Bedrock quota / lets strangers hammer the demo** (accepted
  trade-off — Phong wants everyone to try it) → mitigations that don't gate access:
  unlisted cloudflared URL, `MAX_TURNS_PER_SESSION` cap, Langfuse gives per-session
  usage visibility; if abuse shows up on demo day, re-adding Chainlit password auth is
  a 10-line revert.
- **KG envelope rows don't parse into a clean subgraph** (stub fixtures may return
  tabular projections, not node objects) → parse defensively per canonical-query shape;
  worst case the sidebar shows names + relationship labels from the known query
  templates rather than a full graph — still tells the "context builds up" story.
- **Model over-queries the warehouse without KG context** → tighten system prompt; if
  insufficient, force first tool call to `query_knowledge_graph` via Strands hooks.
- **Version drift** (Strands 1.x moves fast; Langfuse v4) → pin versions in pyproject.

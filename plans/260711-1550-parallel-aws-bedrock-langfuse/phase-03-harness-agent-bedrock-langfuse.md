---
phase: 3
title: "Harness Agent: Strands + AG-UI/CopilotKit on GPT-5.5, Langfuse, Charts"
status: pending
priority: P1
dependencies: [2]
---

# Phase 3: Harness Agent: Strands + AG-UI/CopilotKit on GPT-5.5, Langfuse, Charts

## Overview

Phong's main build — and per Phong's directives (2026-07-11): the harness must be
**visibly agentic** (thoughts, plan, tool selection, where knowledge is retrieved from,
follow-up questions with the user in a loop until context suffices → insight report),
it must **look modern**, and we **adopt existing components instead of building them**
due to the time limit. Chosen stack (research reports
`researcher-260711-1718-GH-3-agentic-harness-framework-report.md` + the AG-UI addendum):

- **Strands Agents SDK** (AWS OSS, 1.x) owns the agent loop: `@tool` functions,
  streamed reasoning/tool events, hooks, first-party Langfuse OTel export.
- **AG-UI protocol + CopilotKit** owns the UI: the **official Strands↔AG-UI
  integration** streams agent events to a small Next.js app using CopilotKit's chat
  components — modern look, human-in-the-loop interrupts, **bi-directional shared
  state** that powers a live KG-context side panel rendered as a real interactive
  graph. **No auth** — open access by Phong's decision: anyone with the demo URL can
  try it.
- Model: **GPT-5.5 via bedrock-mantle** (OpenAI-compatible endpoint), configured as
  Strands' OpenAI provider with a custom base_url.

Developed 100% against Karsten's replay stub (PR #4: `uv run tn`, fixtures in
`governance/fixtures/replay/`, agent guide at `docs/USING-TN.md`).

## Requirements

- Functional: agent implements the **intended loop from USING-TN.md** (kg schema
  bootstrap → term resolve → variant disambiguation **by asking the user via an AG-UI
  human-in-the-loop interrupt** → metric detail → data query → envelope-driven
  narration); persona token on every CLI call; **every reasoning/tool step streamed to
  the UI as AG-UI events** and rendered in the chat timeline; **KG-context side panel
  that grows as the agent explores** (each `query_knowledge_graph` result merges into
  shared state; the React panel re-renders the subgraph — the user watches context
  build up); Plotly chart rendering from query results; pin-to-dashboard;
  md/xlsx/parquet exports.
- Non-functional: every user turn = one Langfuse trace (via Strands OTel) with nested
  generation + tool spans, session + persona tagged; model/CLI/keys all env-configured;
  loop capped by Strands' max-iterations config with a graceful "couldn't answer" path.

## Architecture

```
Next.js + CopilotKit (harness/ui, :3000)          FastAPI AG-UI endpoint (harness/agent, :8000)
  chat timeline (reasoning + tool events)   ◄──── Strands Agent via official AG-UI integration
  KG side panel (graph from shared state)   ◄──── shared state: kg_context {nodes, edges}
  HITL prompt (variant / candidate choice)  ◄──── ask-user interrupt, resumes the run
  Plotly chart component · 📌 pin · exports ◄──── render_chart tool result (spec + rows)
                                                    │
  model = OpenAIModel(client_args={base_url: $OPENAI_BASE_URL,   # bedrock-mantle
                                    api_key:  $OPENAI_API_KEY},  # Bedrock API key
                       model_id=$MODEL_ID)                       # openai.gpt-5.5 — verify day 0
  @tool functions → subprocess: $GOVERNED_CLI_CMD (default `uv run tn`)
        tn kg query|metrics list|metrics describe|query --token $TOKEN ...
        v0.3 envelope (incl. error.code/details) returned as the tool result
  StrandsTelemetry (OTel) ──► Langfuse Cloud /api/public/otel
```

- **Strands owns the loop mechanics** (tool dispatch, reasoning-item handling, retries,
  iteration cap) — no hand-rolled loop. The OpenAI-provider config and the
  bedrock-mantle API surface (Chat Completions vs Responses) are the day-0 verification
  item (phase 5A); fallback if mismatched: Strands' LiteLLM provider or a custom model
  provider.
- **AG-UI is the UI contract** (same philosophy as the `tn` contract): the backend
  emits protocol events (text deltas, tool calls, state patches, interrupts); the
  frontend is a thin CopilotKit consumer. Follow the official Strands AG-UI docs
  (strandsagents.com → community integrations → AG-UI) for the endpoint wiring —
  verify the quickstart runs on **day 1 before building on it** (it's community-tier);
  fallback documented below.
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
  pointed at Langfuse's OTel endpoint (documented first-party both sides). Session id +
  persona set as trace attributes per Langfuse's Strands cookbook. Cost tracking: add
  `openai.gpt-5.5` pricing manually in the Langfuse dashboard.
- Tools map 1:1 onto contract v0.3 commands (CONTRACT.md is the spec, not this plan):
  `query_knowledge_graph(cypher)` → `tn kg query`; `query_warehouse(metric, group_by[],
  grain, filters[], start, end)` → `tn query` flags — the model never writes SQL, the
  `@tool` signature enforces the shape; `list_metrics()` / `describe_metric(key)`
  → `tn metrics list|describe`. At startup, load `tn kg schema` output (labels,
  invariants, canonical Cypher examples) into the system prompt.
- **Ask-the-user loop**: variant disambiguation and candidate selection use AG-UI's
  human-in-the-loop mechanism (CopilotKit renders the choice inline; the agent run
  pauses and resumes with the answer) — this is the "loop until enough context"
  behavior, visible as a step in the timeline and a span in the Langfuse trace.
- **KG-context side panel** (`harness/agent/kg_context.py` + React panel): a
  per-session dict of `{nodes, edges}` keyed by node id. After every
  `query_knowledge_graph` / `describe_metric` call, the backend parses the envelope
  rows (Concept / Metric / Dimension / Table / Constraint nodes, VARIANT_OF /
  MEASURED_BY / HAS_DIMENSION / COMPUTED_FROM / CONSTRAINS edges — the contract §4
  shapes) and merges them into AG-UI **shared state**; the frontend re-renders an
  interactive force-directed graph (node color by label, **newly added nodes
  highlighted**, `_access.readable: false` nodes marked locked — DoD-3's denied metric
  shows up visibly locked). Parse defensively — unknown row shapes are skipped, never
  crash the turn.
- **`render_chart(title, plotly_spec)` tool**: spec arrives WITHOUT data; the backend
  injects the last `tn query` result rows, validates via `plotly.io.from_json`, and
  returns validation errors as the tool result so the model self-corrects — the same
  retry pattern as `METRIC_NOT_FOUND.candidates`. Valid specs render in the frontend
  via react-plotly. `tn`'s `columns[]: {name, type, unit}` maps to axes/format.
- **Dashboard & exports:** 📌 per chart persists `{spec, data, title, persona,
  applied_permissions}` as JSON under `harness/dashboard/`; a dashboard route in the
  Next.js app lays out pinned charts (persona-scoped by construction — Đức's pins are
  visibly South-only). Per-result downloads served by FastAPI: Markdown report
  (narrative + caveats + `applied_permissions` + `provenance.compiled_sql` appendix),
  XLSX (BI), Parquet (analytics) — pandas one-liners.
- Self-correction paths are contract features (full table in USING-TN.md):
  `METRIC_NOT_FOUND.candidates` → surface to user via the HITL prompt, don't pick
  silently; `INVALID_DIMENSION_VALUE.did_you_mean` → retry with canonical spelling;
  `INVALID_DIMENSION.valid_dimensions` → regroup — pass `error.details` through in the
  tool result so the model recovers in one turn.
- Answer narration is envelope-driven: `metadata.applied_permissions` (typed objects with
  `display` strings) → "your view is scoped to region South"; `warnings` (`STALE_DATA`,
  `ROW_LIMIT`) → caveats; `provenance.compiled_sql` + `constraint_keys` → show-your-work.
  A `Metric` node with `_access.readable: false` → the "exists but you can't see it" beat.
- System prompt encodes the governed-BI stance and USING-TN.md's intended loop:
  multi-round KG exploration first; parent-Concept-without-MEASURED_BY = ask the user
  which variant, never guess; canonical Cypher verbatim; VND/tỷ formatting; ratios arrive
  as 0–1 fractions — percent formatting is the harness's job.

## Related Code Files

- Create (backend): `harness/agent/__init__.py`, `harness/agent/tools.py` (@tool
  wrappers → `GOVERNED_CLI_CMD` subprocess), `harness/agent/model.py` (Strands OpenAI
  provider → bedrock-mantle), `harness/agent/tracing.py` (StrandsTelemetry → Langfuse),
  `harness/agent/system_prompt.py`, `harness/agent/kg_context.py` (envelope → shared-state
  subgraph), `harness/agent/charts.py` (Plotly validation + data injection),
  `harness/agent/exports.py` (md/xlsx/parquet), `harness/agent/server.py` (FastAPI
  AG-UI endpoint + persona/session handling + `MAX_TURNS_PER_SESSION` guard + download
  routes), `harness/dashboard/` (pinned-chart JSON)
- Create (frontend): `harness/ui/` — Next.js + CopilotKit app: chat timeline, persona
  picker (Mai/executive, Đức/regional-manager-South, Lan/marketing-ops, Bình/analyst),
  KG graph side panel (force-directed, from shared state), Plotly chart component,
  dashboard route, export buttons. Use CopilotKit's prebuilt components — no custom
  design system.
- Create: `harness/.env.example` (`MODEL_ID=openai.gpt-5.5`, `OPENAI_BASE_URL`
  (bedrock-mantle), `OPENAI_API_KEY` (Bedrock API key), `GOVERNED_CLI_CMD`,
  `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL`, `MAX_TURNS_PER_SESSION`)
- Modify: `harness/pyproject.toml` (add `strands-agents[otel]`, the Strands AG-UI
  integration package, fastapi, uvicorn, plotly, pandas, openpyxl, pyarrow; pin
  versions)

## Implementation Steps

1. **Day-1 spike (go/no-go):** run the official Strands↔AG-UI + CopilotKit quickstart
   with a dummy tool; confirm reasoning/tool events, HITL interrupt, and shared state
   reach the browser. If the community integration stalls > half a day, fall back to
   the preserved Chainlit design (git history has it) and keep everything else.
2. `model.py` + `tracing.py`: Strands agent with OpenAI provider pointed at
   bedrock-mantle; StrandsTelemetry → Langfuse; smoke-test a plain question end-to-end
   and confirm the trace tree lands in Langfuse (needs Phase 5A key). This step also
   settles the Chat-Completions-vs-Responses question.
3. `tools.py`: five `@tool` functions shelling out to `GOVERNED_CLI_CMD`; exit 1 with
   envelope → tool result carrying `error.code` + `error.details`; non-zero without
   parseable envelope → treat as `INTERNAL` per contract.
4. `system_prompt.py`: governed-analyst prompt built from `tn kg schema` output +
   USING-TN.md loop + verbatim-Cypher rule + ask-don't-guess rule + narration rules.
5. `server.py` + `harness/ui/`: AG-UI endpoint with persona/session wiring (open
   access, `MAX_TURNS_PER_SESSION` guard; new chat = new Langfuse session id); Next.js
   app with chat, persona picker, HITL rendering.
6. `kg_context.py` + KG panel: envelope → shared-state merge; force-directed graph
   component; verify on the DoD-1 exploration rounds.
7. `charts.py` + `exports.py` + frontend chart/dashboard/export pieces.
8. Run the Definition-of-Done script below end-to-end; fix until green.

## Definition of Done — the four demo conversations (all on the stub)

Every scenario below uses only requests fixtured in PR #4 (`docs/USING-TN.md`); each must
work as a live chat **with the agent's reasoning and tool steps visible in the chat
timeline**, and the full trace visible in Langfuse. **Phase 3 is done when all four pass
twice in a row.**

**DoD-1 · Ambiguity + trap caveat (Bình, analyst).**
"How is our customer retention doing by channel?" → agent resolves 'retention' via
canonical KG query → parent Concept with 2 variants (repeat-purchase vs loyalty-activity)
→ agent **asks the user via the HITL prompt** which; user picks repeat-purchase → agent
loads metric detail (dims/caveats/tables) → `tn query --metric repeat_purchase_rate_90d
--group-by channel` → answer shows a ratio formatted as %, names the caveat(s), renders a
bar chart via `render_chart`. ✅ when: agent asked instead of guessing; chart rendered
from real result rows; caveat named in prose; KG-exploration steps visible in the UI;
**the side panel visibly grows across the turn** (Concept → two variants → chosen metric
→ its dimensions/tables appear in sequence).

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
narrations are accurate; agent stays helpful (offers what she CAN see, e.g. net_revenue);
**the denied metric appears locked in the KG side panel**.

**DoD-4 · Self-correction (Mai).**
"Show me revenue for offline stores" → `--metric revenue` returns
`METRIC_NOT_FOUND` + candidates → agent surfaces candidates (gross vs net) via the HITL
prompt, user picks net → `--filter "channel = 'offline'"` returns
`INVALID_DIMENSION_VALUE` + `did_you_mean: in_store` → agent retries with `in_store` and
answers. ✅ when: both recoveries happen (one asks the user, one auto-corrects), visible
as distinct steps in the timeline and tool spans in the Langfuse trace.

**Plus, on any DoD scenario:** 📌 pin the chart → it appears on the dashboard route with
persona + permissions; the three export downloads produce a readable .md, an .xlsx that
opens in Excel/Numbers, and a .parquet that `pandas.read_parquet` round-trips.

## Success Criteria

- [ ] DoD-1…DoD-4 pass twice consecutively on the stub, each as a natural chat.
- [ ] Agentic visibility: reasoning + every tool call streamed as AG-UI events and
  rendered in the chat timeline.
- [ ] KG side panel: grows during DoD-1's exploration rounds; DoD-3 shows Lan's denied
  metric as a locked node; resets on new chat.
- [ ] Langfuse trace tree per turn (via Strands OTel): trace → agent span →
  N×(generation | tool span), session + persona tagged, token usage populated.
- [ ] Chart pipeline: invalid spec from the model self-corrects via validation-error
  round-trip (force once by prompt to verify).
- [ ] Pin + exports work per the DoD rider above.
- [ ] No harness code imports Karsten's Python modules (subprocess + files only).

## Risk Assessment

- **AG-UI↔Strands integration is community-tier** (biggest schedule risk) → day-1
  go/no-go spike (step 1); the Chainlit fallback design is fully specified in git
  history and costs ~1 day to restore. Do not sink more than half a day into the spike.
- **bedrock-mantle API surface mismatch**: Strands' OpenAI provider speaks Chat
  Completions; if `openai.gpt-5.5` on bedrock-mantle is Responses-only, switch to
  Strands' LiteLLM provider or a custom model provider. Settled in step 2 / phase 5A.
- **Frontend scope creep** (React is a time sink) → CopilotKit prebuilt components
  only, one page + one dashboard route, no custom design system; the KG panel is one
  graph library component fed by shared state.
- **LLM Cypher misses replay fixtures** (exact-match) → verbatim-canonical-queries rule
  in the system prompt; if GPT-5.5 still paraphrases, wrap `query_knowledge_graph` to
  template the two canonical queries harness-side (tool args become `term_regex` /
  `metric_key` instead of raw Cypher) — contract-legal and stub-proof.
- **Open access burns Bedrock quota / lets strangers hammer the demo** (accepted
  trade-off — Phong wants everyone to try it) → unlisted cloudflared URL,
  `MAX_TURNS_PER_SESSION` cap, Langfuse per-session usage visibility.
- **KG envelope rows don't parse into a clean subgraph** (stub fixtures may return
  tabular projections, not node objects) → parse defensively per canonical-query shape;
  worst case the panel shows names + relationship labels from the known query
  templates — still tells the "context builds up" story.
- **Model over-queries the warehouse without KG context** → tighten system prompt; if
  insufficient, force first tool call to `query_knowledge_graph` via Strands hooks.
- **Version drift** (Strands 1.x, AG-UI, CopilotKit all move fast) → pin versions in
  pyproject + package.json.

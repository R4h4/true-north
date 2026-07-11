---
phase: 3
title: "Harness Agent: GPT-5.5 + Langfuse + Charts"
status: pending
priority: P1
dependencies: [2]
---

# Phase 3: Harness Agent: GPT-5.5 + Langfuse + Charts

## Overview

Phong's main build: the agent loop on **GPT-5.5 via Bedrock's OpenAI-compatible
Responses API** with tools (knowledge graph, warehouse, charts) calling the governed CLI,
fully traced in Langfuse, behind a Streamlit chat with a persona picker. Developed 100%
against Karsten's replay stub (PR #4: `uv run tn`, fixtures in
`governance/fixtures/replay/`, agent guide at `docs/USING-TN.md`).

## Requirements

- Functional: multi-turn tool-use loop implementing the **intended loop from
  USING-TN.md** (kg schema bootstrap → term resolve → variant disambiguation with the
  user → metric detail → data query → envelope-driven narration); persona token on every
  CLI call; **Vega-Lite chart rendering** from query results; pin-to-dashboard;
  md/xlsx/parquet exports.
- Non-functional: every user turn = one Langfuse trace with nested generation + tool
  spans, session + persona tagged; model/CLI/keys all env-configured; loop hard-capped
  (max 10 iterations) with a graceful "couldn't answer" path.

## Architecture

```
Streamlit chat ── run_agent(question, persona)          harness/agent/
                     │  @observe span, propagate_attributes(user_id=persona, session_id=chat)
                     ├─ openai_client.responses.create(model=$MODEL_ID,  # openai.gpt-5.5 — verify day 0
                     │        base_url=$OPENAI_BASE_URL,  # bedrock-mantle .../openai/v1
                     │        tools=[query_knowledge_graph, query_warehouse,
                     │               list_metrics, describe_metric, render_chart])
                     │    generation traced via langfuse.openai drop-in (usage auto-captured)
                     ├─ tool dispatch → subprocess: $GOVERNED_CLI_CMD (default `uv run tn`)
                     │     tn kg query|metrics list|metrics describe|query --token $TOKEN ...
                     │     @observe span per tool call; v0.3 envelope → function_call_output
                     └─ render_chart → validate Vega-Lite spec, inject last result rows,
                           st.vega_lite_chart · 📌 pin → st.session_state.dashboard
```

- Responses-API tool-use mechanics: define `tools=[{type: "function", name, parameters}]`;
  the model returns `function_call` output items; append each result as a
  `function_call_output` item (with the matching `call_id`) to the next request's input —
  follow the AWS "Get started with OpenAI models on Bedrock" doc + OpenAI Responses docs,
  not memory. GPT-5.5 is a reasoning model: pass reasoning items back with the
  conversation as the docs require (or use `previous_response_id` if bedrock-mantle
  supports server-side state — verify day 0); reasoning tokens bill as output.
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
- Streamlit reruns the whole script on every interaction: conversation history, Langfuse
  session id, persona, **last query result, and pinned dashboard charts** live in
  `st.session_state`; call `langfuse.flush()` at the end of each turn or traces are lost
  on rerun.
- Langfuse SDK **v4**: try the **`langfuse.openai` drop-in** first (wraps the OpenAI
  client; generations + token usage auto-captured — verify it tolerates the
  bedrock-mantle base URL); keep `@observe` spans for the agent loop and tool calls
  either way. Cost tracking: add `openai.gpt-5.5` pricing manually in the Langfuse
  dashboard later.
- Tools map 1:1 onto contract v0.3 commands (CONTRACT.md is the spec, not this plan):
  `query_knowledge_graph(cypher)` → `tn kg query`; `query_warehouse(metric, group_by[],
  grain, filters[], start, end)` → `tn query` flags — the model never writes SQL, the
  function-tool JSON schema enforces the shape; `list_metrics()` / `describe_metric(key)`
  → `tn metrics list|describe`. At startup, load `tn kg schema` output (labels,
  invariants, canonical Cypher examples) into the system prompt.
- **`render_chart(title, vega_lite_spec)` tool** (research report
  `researcher-260711-1703-harness-chart-dashboard-oss-report.md`): spec arrives WITHOUT
  data; the harness injects the last `tn query` result rows as inline `values` (token
  savings + the model can't invent numbers), validates against the Vega-Lite JSON schema,
  and returns validation errors as the tool result so the model self-corrects — the same
  retry pattern as `METRIC_NOT_FOUND.candidates`. Render via `st.vega_lite_chart`.
  `tn`'s `columns[]: {name, type, unit}` maps directly to encodings.
- **Dashboard & exports:** 📌 per chart appends `{spec, data, title, persona,
  applied_permissions}` to `st.session_state.dashboard`; a Dashboard tab lays them out
  (persona-scoped by construction — Đức's pins are visibly South-only). Per-result
  download buttons: Markdown report (narrative + caveats + `applied_permissions` +
  `provenance.compiled_sql` appendix), XLSX (BI), Parquet (analytics) — pandas one-liners.
- Self-correction paths are contract features (full table in USING-TN.md):
  `METRIC_NOT_FOUND.candidates` → surface to user, don't pick silently;
  `INVALID_DIMENSION_VALUE.did_you_mean` → retry with canonical spelling;
  `INVALID_DIMENSION.valid_dimensions` → regroup — pass `error.details` through in
  function_call_output so the model recovers in one turn.
- Answer narration is envelope-driven: `metadata.applied_permissions` (typed objects with
  `display` strings) → "your view is scoped to region South"; `warnings` (`STALE_DATA`,
  `ROW_LIMIT`) → caveats; `provenance.compiled_sql` + `constraint_keys` → show-your-work.
  A `Metric` node with `_access.readable: false` → the "exists but you can't see it" beat.
- System prompt encodes the governed-BI stance and USING-TN.md's intended loop:
  multi-round KG exploration first; parent-Concept-without-MEASURED_BY = ask the user
  which variant, never guess; canonical Cypher verbatim; VND/tỷ formatting; ratios arrive
  as 0–1 fractions — percent formatting is the harness's job.

## Related Code Files

- Create: `harness/agent/__init__.py`, `harness/agent/loop.py`, `harness/agent/tools.py`,
  `harness/agent/llm_client.py`, `harness/agent/tracing.py`,
  `harness/agent/system_prompt.py`, `harness/agent/charts.py` (spec validation + data
  injection), `harness/agent/exports.py` (md/xlsx/parquet)
- Create: `harness/app.py` (Streamlit: chat + Dashboard tab), `harness/.env.example`
  (`MODEL_ID=openai.gpt-5.5`, `OPENAI_BASE_URL` (bedrock-mantle), `OPENAI_API_KEY`
  (Bedrock API key), `GOVERNED_CLI_CMD`, `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL`,
  `DEMO_PASSPHRASE`)
- Modify: `harness/pyproject.toml` (add openai, langfuse, streamlit, pandas, openpyxl,
  pyarrow, jsonschema)

## Implementation Steps

1. `llm_client.py`: OpenAI SDK client pointed at bedrock-mantle (base URL + Bedrock API
   key from env), wrapped with `langfuse.openai`; smoke-test with a plain question (needs
   Phase 5A key). Iterate on gpt-oss if cost-nervous; ship on GPT-5.5.
2. `tools.py`: five function-tool definitions + dispatcher shelling out to
   `GOVERNED_CLI_CMD`; exit 1 with envelope → `function_call_output` carrying
   `error.code` + `error.details`; non-zero without parseable envelope → treat as
   `INTERNAL` per contract.
3. `loop.py`: Responses loop — while output contains `function_call` items, execute and
   append `function_call_output` items (echoing reasoning items per docs); stop on plain
   text output or 10 iterations.
4. `system_prompt.py`: governed-analyst prompt built from `tn kg schema` output +
   USING-TN.md loop + verbatim-Cypher rule + narration rules.
5. `charts.py` + `exports.py`: Vega-Lite validation/injection; md/xlsx/parquet writers.
6. `app.py`: chat + persona dropdown (Mai/executive, Đức/regional-manager-South,
   Lan/marketing-ops, Bình/analyst), Dashboard tab, `st.session_state` for
   history/session/result/pins, per-turn `langfuse.flush()`, `DEMO_PASSPHRASE` gate;
   new chat = new Langfuse session id.
7. Run the Definition-of-Done script below end-to-end; fix until green.

## Definition of Done — the four demo conversations (all on the stub)

Every scenario below uses only requests fixtured in PR #4 (`docs/USING-TN.md`); each must
work as a live chat, with the full trace visible in Langfuse. **Phase 3 is done when all
four pass twice in a row.**

**DoD-1 · Ambiguity + trap caveat (Bình, analyst).**
"How is our customer retention doing by channel?" → agent resolves 'retention' via
canonical KG query → parent Concept with 2 variants (repeat-purchase vs loyalty-activity)
→ agent asks the user which; user picks repeat-purchase → agent loads metric detail
(dims/caveats/tables) → `tn query --metric repeat_purchase_rate_90d --group-by channel`
→ answer shows a ratio formatted as %, names the caveat(s), renders a bar chart via
`render_chart`. ✅ when: agent asked instead of guessing; chart rendered from real result
rows; caveat named in prose.

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
`METRIC_NOT_FOUND` + candidates → agent surfaces candidates (gross vs net), user picks
net → `--filter "channel = 'offline'"` returns `INVALID_DIMENSION_VALUE` +
`did_you_mean: in_store` → agent retries with `in_store` and answers. ✅ when: both
recoveries happen (one asks the user, one auto-corrects), visible as distinct tool spans
in the Langfuse trace.

**Plus, on any DoD scenario:** 📌 pin the chart → it appears on the Dashboard tab with
persona + permissions; the three download buttons produce a readable .md, an .xlsx that
opens in Excel/Numbers, and a .parquet that `pandas.read_parquet` round-trips.

## Success Criteria

- [ ] DoD-1…DoD-4 pass twice consecutively on the stub, each as a natural chat.
- [ ] Langfuse trace tree per turn: trace → agent span → N×(generation | tool span),
  session + persona tagged, token usage populated.
- [ ] Chart pipeline: invalid spec from the model self-corrects via validation-error
  round-trip (force once by prompt to verify).
- [ ] Pin + exports work per the DoD rider above.
- [ ] No harness code imports Karsten's Python modules (subprocess + files only).

## Risk Assessment

- **Responses-API item-format mistakes / reasoning-item handling** (most likely bug) →
  code from the AWS + OpenAI doc examples first, golden-log one full request/response
  pair into a fixture test; verify `previous_response_id` support on bedrock-mantle
  before relying on it.
- **LLM Cypher misses replay fixtures** (exact-match) → verbatim-canonical-queries rule
  in the system prompt; if GPT-5.5 still paraphrases, wrap `query_knowledge_graph` to
  template the two canonical queries harness-side (tool args become `term_regex` /
  `metric_key` instead of raw Cypher) — contract-legal and stub-proof.
- **`langfuse.openai` drop-in rejects the bedrock-mantle base URL or misses usage
  fields** → fall back to manual `@observe(as_type="generation")` wrapping; the Langfuse
  research report has the exact call shapes.
- **Model over-queries the warehouse without KG context** → tighten system prompt; if
  insufficient, force first tool call to `query_knowledge_graph` programmatically.
- **Langfuse v4 keyword drift** (4-month-old SDK) → pin the version in pyproject.

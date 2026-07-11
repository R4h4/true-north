---
phase: 3
title: "Harness Agent: Bedrock + Langfuse"
status: pending
priority: P1
dependencies: [2]
---

# Phase 3: Harness Agent: Bedrock + Langfuse

## Overview

Phong's main build: the agent loop on **GPT-5.5 via Bedrock's OpenAI-compatible
Responses API** with tools (knowledge graph, warehouse) calling the governed CLI, fully
traced in Langfuse, behind a Streamlit chat with a persona picker. Developed 100% against
the stub `tn` CLI (Phase 2 fixtures).

## Requirements

- Functional: multi-turn tool-use loop; persona selection sets the token for every CLI
  call; KG-first behavior (resolve business terms before querying warehouse); permission
  denials and `notices` surfaced in the answer text.
- Non-functional: every user turn = one Langfuse trace with nested generation + tool
  spans, session + persona tagged; model/CLI/keys all env-configured; loop hard-capped
  (max 10 iterations) with a graceful "couldn't answer" path.

## Architecture

```
Streamlit chat ── run_agent(question, persona)          harness/agent/
                     │  @observe span, propagate_attributes(user_id=persona, session_id=chat)
                     ├─ openai_client.responses.create(model=$MODEL_ID,  # openai.gpt-5.5 — verify day 0
                     │        base_url=$OPENAI_BASE_URL,  # bedrock-mantle .../openai/v1
                     │        tools=[query_knowledge_graph, query_warehouse, ...])
                     │    generation traced via langfuse.openai drop-in (usage auto-captured)
                     └─ tool dispatch → subprocess: $GOVERNED_CLI_CMD (default `uv run tn`)
                          tn kg query|metrics list|metrics describe|query --token $TOKEN ...
                          @observe span per tool call; v0.3 envelope → function_call_output
```

- Responses-API tool-use mechanics: define `tools=[{type: "function", name, parameters}]`;
  the model returns `function_call` output items; append each result as a
  `function_call_output` item (with the matching `call_id`) to the next request's input —
  follow the AWS "Get started with OpenAI models on Bedrock" doc + OpenAI Responses docs,
  not memory. GPT-5.5 is a reasoning model: pass reasoning items back with the
  conversation as the docs require (or use `previous_response_id` if bedrock-mantle
  supports server-side state — verify day 0); reasoning tokens bill as output.
- Streamlit reruns the whole script on every interaction: conversation history, Langfuse
  session id, and persona live in `st.session_state`; call `langfuse.flush()` at the end
  of each turn or traces are lost on rerun.
- Langfuse SDK **v4**: try the **`langfuse.openai` drop-in** first (wraps the OpenAI
  client; generations + token usage auto-captured — verify it tolerates the
  bedrock-mantle base URL); keep `@observe` spans for the agent loop and tool calls
  either way. Cost tracking: add `openai.gpt-5.5` pricing manually in the Langfuse
  dashboard later.
- Tools map 1:1 onto contract v0.3 commands (CONTRACT.md is the spec, not this plan):
  `query_knowledge_graph(cypher)` → `tn kg query`; `query_warehouse(metric, group_by[],
  grain, filters[], start, end)` → `tn query` flags — the model never writes SQL, the
  function-tool JSON schema enforces the shape; `list_metrics()` / `describe_metric(key)`
  → `tn metrics list|describe`. At startup, load `tn kg schema` (labels, invariants,
  canonical Cypher examples) into the system prompt — the contract hands us the agent's
  Cypher cookbook.
- Self-correction paths are contract features: `METRIC_NOT_FOUND` carries `candidates[]`,
  `INVALID_DIMENSION_VALUE` carries `did_you_mean` — pass `error.details` through in
  toolResults so the model recovers in one turn instead of flailing.
- Answer narration is envelope-driven: `metadata.applied_permissions` (typed objects with
  `display` strings) → "your view is scoped to region South"; `warnings` (`STALE_DATA`,
  `ROW_LIMIT`) → caveats; `provenance.compiled_sql` + `constraint_keys` → show-your-work.
  A `Metric` node with `_access.readable: false` → the "exists but you can't see it" beat.
- System prompt encodes the governed-BI stance and the contract's intended usage pattern:
  multi-round KG exploration first (resolve term → parent concept → variants → metric +
  constraints, per §4.2 invariants: parent-without-MEASURED_BY = ask the user which
  variant); surface ambiguity instead of guessing; VND/tỷ formatting; ratios arrive as
  0–1 fractions — percent formatting is the harness's job.

## Related Code Files

- Create: `harness/agent/__init__.py`, `harness/agent/loop.py`, `harness/agent/tools.py`,
  `harness/agent/llm_client.py`, `harness/agent/tracing.py`,
  `harness/agent/system_prompt.py`
- Create: `harness/app.py` (Streamlit), `harness/.env.example` (`MODEL_ID=openai.gpt-5.5`,
  `OPENAI_BASE_URL` (bedrock-mantle), `OPENAI_API_KEY` (Bedrock API key),
  `GOVERNED_CLI_CMD`, `GOVERNED_CLI_TOKEN` per persona,
  `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL`, `DEMO_PASSPHRASE`)
- Modify: `harness/pyproject.toml` (add openai, langfuse, streamlit)

## Implementation Steps

1. `llm_client.py`: OpenAI SDK client pointed at bedrock-mantle (base URL + Bedrock API
   key from env), wrapped with `langfuse.openai`; smoke-test with a plain question (needs
   Phase 5A key). Iterate on gpt-oss if cost-nervous; ship on GPT-5.5.
2. `tools.py`: function-tool definitions (`query_knowledge_graph`, `query_warehouse`,
   `list_metrics`, `describe_metric`) mapping to `tn` subcommand flags + dispatcher
   shelling out to `GOVERNED_CLI_CMD`; exit 1 with envelope → `function_call_output`
   carrying `error.code` + `error.details`; non-zero without parseable envelope → treat
   as `INTERNAL` per contract.
3. `loop.py`: Responses loop — while output contains `function_call` items, execute and
   append `function_call_output` items (echoing reasoning items per docs); stop on plain
   text output or 10 iterations.
4. `system_prompt.py`: governed-analyst prompt (KG-first, cite caveats/notices, VND/tỷ
   formatting).
5. `app.py`: chat + persona dropdown (the four contract tokens from CONTRACT.md §1 —
   Mai/executive, Đức/regional-manager-South, Lan/marketing-ops, Bình/analyst),
   history/session in `st.session_state`, per-turn `langfuse.flush()`, and a
   shared-passphrase gate (env `DEMO_PASSPHRASE`) so a public URL can't burn Bedrock
   quota; new chat = new Langfuse session id.
6. Manual eval: run 3–4 TRAPS.md questions against the stub; verify nested traces, token
   usage, persona tags in Langfuse UI.

## Success Criteria

- [ ] "Doanh thu (revenue) last quarter?" produces: KG tool call → warehouse tool call →
  answer that names the gross-vs-net-of-returns caveat.
- [ ] Persona switch changes both the answer and the `user_id` on the Langfuse trace.
- [ ] A `PERMISSION_DENIED` tool result yields a polite "you don't have access to X"
  answer, not a retry loop.
- [ ] Langfuse trace tree matches: trace → agent span → N×(generation | tool span).

## Risk Assessment

- **Responses-API item-format mistakes / reasoning-item handling** (most likely bug) →
  code from the AWS + OpenAI doc examples first, golden-log one full request/response
  pair into a fixture test; verify `previous_response_id` support on bedrock-mantle
  before relying on it.
- **`langfuse.openai` drop-in rejects the bedrock-mantle base URL or misses usage
  fields** → fall back to manual `@observe(as_type="generation")` wrapping (the original
  plan); the Langfuse research report has the exact call shapes.
- **Model over-queries the warehouse without KG context** → tighten system prompt; if
  insufficient, force first tool call to `query_knowledge_graph` programmatically.
- **Langfuse v4 keyword drift** (4-month-old SDK) → pin the version in pyproject.

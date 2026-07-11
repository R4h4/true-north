---
phase: 3
title: "Harness Agent: Bedrock + Langfuse"
status: pending
priority: P1
dependencies: [2]
---

# Phase 3: Harness Agent: Bedrock + Langfuse

## Overview

Phong's main build: the agent loop on Bedrock's Converse API with two tools (knowledge
graph, warehouse) calling the governed CLI, fully traced in Langfuse, behind a Streamlit
chat with a persona picker. Developed 100% against the stub `tn` CLI (Phase 2 fixtures).

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
                     ├─ bedrock.converse(modelId=$BEDROCK_MODEL_ID,  # global.anthropic.claude-sonnet-5 — verify day 0
                     │                   toolConfig={query_knowledge_graph, query_warehouse})
                     │    @observe generation: usage_details from response["usage"]
                     └─ tool dispatch → subprocess: $GOVERNED_CLI_CMD (default `uv run tn`)
                          tn kg query|metrics list|metrics describe|query --token $TOKEN ...
                          @observe span per tool call; v0.3 envelope passed back as toolResult
```

- Converse tool-use mechanics: content blocks are `{"toolUse": {...}}` and results are
  sent back as `{"toolResult": {"toolUseId": ..., "content": [{"json": ...}]}}` —
  follow the AWS "Call a tool with the Converse API" doc, not memory. (The research
  report's sketch uses Anthropic-API style blocks; verify against AWS docs when coding.)
- Sonnet 5 has always-on adaptive reasoning: `reasoningContent` blocks appear in responses
  and **must be echoed back verbatim** in the message history on subsequent turns of the
  tool loop; reasoning tokens bill (and burn quota) as output tokens.
- Streamlit reruns the whole script on every interaction: conversation history, Langfuse
  session id, and persona live in `st.session_state`; call `langfuse.flush()` at the end
  of each turn or traces are lost on rerun.
- Langfuse SDK **v4**: `@observe(as_type="generation")` wrapper around the converse call,
  `propagate_attributes` for session/user. No Bedrock auto-instrumentation exists —
  wrapping is manual. Cost tracking: log token counts now; optional custom model pricing
  in Langfuse dashboard later.
- Tools map 1:1 onto contract v0.3 commands (CONTRACT.md is the spec, not this plan):
  `query_knowledge_graph(cypher)` → `tn kg query`; `query_warehouse(metric, group_by[],
  grain, filters[], start, end)` → `tn query` flags — the model never writes SQL, Converse
  inputSchema enforces the shape; `list_metrics()` / `describe_metric(key)` → `tn metrics
  list|describe`. At startup, load `tn kg schema` (labels, invariants, canonical Cypher
  examples) into the system prompt — the contract hands us the agent's Cypher cookbook.
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
  `harness/agent/bedrock_client.py`, `harness/agent/tracing.py`,
  `harness/agent/system_prompt.py`
- Create: `harness/app.py` (Streamlit), `harness/.env.example` (`AWS_REGION`,
  `BEDROCK_MODEL_ID`, `GOVERNED_CLI_CMD`, `GOVERNED_CLI_TOKEN` per persona,
  `LANGFUSE_PUBLIC_KEY/SECRET_KEY/BASE_URL`)
- Modify: `harness/pyproject.toml` (add boto3, langfuse, streamlit)

## Implementation Steps

1. `bedrock_client.py`: converse wrapper with Langfuse generation tracing; smoke-test with
   a plain question (needs Phase 5A creds). Iterate on Haiku 4.5 if cost-nervous; ship on
   Sonnet 5.
2. `tools.py`: toolSpec definitions (`query_knowledge_graph`, `query_warehouse`,
   `list_metrics`, `describe_metric`) mapping to `tn` subcommand flags + dispatcher
   shelling out to `GOVERNED_CLI_CMD`; exit 1 with envelope → toolResult carrying
   `error.code` + `error.details`; non-zero without parseable envelope → treat as
   `INTERNAL` per contract.
3. `loop.py`: converse loop until `stopReason != "tool_use"` or 10 iterations.
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

- **Converse block-format mistakes** (most likely bug) → code from AWS doc example first,
  golden-log one full request/response pair into a fixture test.
- **Model over-queries the warehouse without KG context** → tighten system prompt; if
  insufficient, force first tool call to `query_knowledge_graph` programmatically.
- **Langfuse v4 keyword drift** (4-month-old SDK) → pin the version in pyproject; the
  research report has the exact call shapes.

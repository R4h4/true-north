# Research: existing agentic harness (framework + UI) instead of hand-rolled loop

Date: 2026-07-11 17:18 ICT. Trigger: Phong — harness must be *visibly* agentic
(thoughts, plan, tool choice, where knowledge came from, follow-up questions in a loop
until enough context → insight report). Time-boxed hackathon → adopt, don't build.

## Recommendation

**Strands Agents SDK (agent brain) + Chainlit (chat UI).** Both open source, both with
first-party Langfuse/observability docs. Replaces the hand-rolled `loop.py` +
Streamlit-rerun plumbing from the earlier phase-3 draft.

### Strands Agents (AWS OSS, 1.x GA) — the loop

- Model-driven agent loop: `@tool`-decorated Python functions, structured output,
  hooks to intercept any step. Multi-agent not needed here but present.
- **Bedrock is the default provider**; as of June 2026 first-class providers incl.
  OpenAI (custom `client_args` → base_url = bedrock-mantle) and anything via LiteLLM.
- `stream_async` yields **reasoning, text, and tool-use events in real time** — exactly
  the "show thoughts/plan/tool choice" requirement; maps 1:1 onto Chainlit steps.
- **Langfuse integration is documented first-party**: `pip install 'strands-agents[otel]'`,
  `StrandsTelemetry` → Langfuse OTel endpoint (`/api/public/otel`). Full trace tree
  (LLM calls, tool calls, latencies, usage) with zero manual `@observe` wrapping.
- AWS-native story = on-theme for the hackathon.
- Sources: https://strandsagents.com/ · https://aws.amazon.com/blogs/opensource/introducing-strands-agents-1-0-production-ready-multi-agent-orchestration-made-simple/ ·
  https://langfuse.com/integrations/frameworks/strands-agents ·
  https://strandsagents.com/docs/user-guide/observability-evaluation/traces/

### Chainlit — the UI

- **Step tree built in**: `cl.Step(type="tool")` renders nested thoughts/tool calls;
  chain-of-thought display modes `hidden|tool_call|full`. No hand-built expanders.
- **`cl.AskUserMessage` pauses the agent mid-run to ask the user** — the follow-up-question
  loop (DoD-1 "which retention variant?") is a native primitive, vs. Streamlit where
  mid-run HITL fights the rerun model.
- `cl.Plotly` element renders charts inline; password-auth callback covers the
  `DEMO_PASSPHRASE` gate; persistent sessions.
- Maintenance: original team stepped back May 2025; now formally community-maintained
  (@Chainlit/chainlit-maintainers), regular releases. Acceptable for a demo.
- Sources: https://github.com/chainlit/chainlit · https://docs.chainlit.io/api-reference/elements/plotly ·
  https://deepwiki.com/Chainlit/chainlit/4-step-and-message-system

### Consequence: charts switch Vega-Lite → Plotly JSON

Earlier report picked Vega-Lite for `st.vega_lite_chart`. Chainlit renders **Plotly**
natively (Vega-Lite would need a custom JSX element). New evidence → reverse:
`render_chart` tool emits a Plotly figure spec (no data), harness injects rows,
validates via `plotly.io.from_json` try/except → error returned for self-correction.
Same pattern, zero UI glue.

## Alternatives rejected

| Option | Why not |
|---|---|
| Hand-rolled Responses loop + Streamlit (prior plan) | Slowest path to visible reasoning + mid-run HITL; exactly what user vetoed |
| OpenAI Agents SDK | Works (custom base_url, Langfuse via OpenInference) but no UI, no AWS story; keep as fallback if Strands↔bedrock-mantle fails |
| CopilotKit/AG-UI | Full JS app stack — too heavy for the week |
| Gradio | Weaker step/HITL primitives than Chainlit |
| WrenAI | Already rejected (full GenBI product, own semantic layer — bypasses `tn`) |

## Addendum (2026-07-11 17:35 ICT) — UI superseded: Chainlit → AG-UI + CopilotKit

Phong: Chainlit "looks kinda old and ugly". Re-evaluated; **official Strands↔AG-UI
integration exists** (https://strandsagents.com/docs/community/integrations/ag-ui/ ·
https://www.copilotkit.ai/blog/aws-strands-agents-now-compatible-with-ag-ui). AG-UI =
protocol between agent backend and frontend (AWS AgentCore runs it natively since
Mar 2026). CopilotKit React components = modern chat, HITL interrupts, bi-directional
shared state → KG side panel as real interactive graph. Strands backend + Langfuse OTel
unchanged — swap touches UI layer only. Costs: small Next.js app in `harness/ui/`,
~1 extra day, community-tier integration → day-1 go/no-go spike; Chainlit design kept
in git history as ~1-day fallback. Onyx also evaluated same day and rejected (full
platform: own agent loop, no Langfuse, frontend fork needed for side panel — same
disqualifier class as WrenAI). Open WebUI rejected: pipe foot-guns, no-auth mode shares
one chat history across visitors — bad for the open demo.

## Unresolved questions

1. **bedrock-mantle API surface for `openai.gpt-5.5`**: Chat Completions, Responses, or
   both? Strands' OpenAI provider speaks Chat Completions. Verify day 0 (phase 5A smoke
   test). If Responses-only: use Strands' LiteLLM provider or a custom model provider.
2. Strands version to pin — check latest on PyPI at implementation time.

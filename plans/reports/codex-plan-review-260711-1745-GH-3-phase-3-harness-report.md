# Codex review of phase-3 harness plan

Date: 2026-07-11 17:45 ICT. Reviewer: Codex CLI 0.142.5, model **gpt-5.5, reasoning
xhigh** (user asked for gpt-5.6; ChatGPT-account Codex rejects that id — substitution
disclosed). Read-only sandbox over the repo; 185k tokens. Subject:
`plans/260711-1550-parallel-aws-bedrock-langfuse/phase-03-harness-agent-bedrock-langfuse.md`
(AG-UI/CopilotKit revision) + CONTRACT.md + parent plan.

## Verdict

**Executable with changes, not as written.** Core idea sound; would burn time on a
wrong Bedrock provider path, assumes unmerged replay fixtures as fact, and leaves
session/proxy/streaming/quota details vague.

## Findings (as reported by Codex; verification status added by Claude)

- **BLOCKER · provider config wrong** — GPT-5.5 on bedrock-mantle is **Responses API
  exclusively** (Chat Completions + Converse unsupported per AWS model card); Strands
  has a dedicated `OpenAIResponsesModel`. Plan said generic `OpenAIModel` + "verify
  Chat-vs-Responses day 0". → **VERIFIED via AWS + Strands docs** (see sources below);
  plan fixed: `OpenAIResponsesModel` from the start.
- **BLOCKER · fixtures not in checkout** — DoD claims runnable on stub, but PR #4
  (stub, `governance/fixtures/replay/`, `docs/USING-TN.md`, conformance) is an unmerged
  draft; current checkout has only the 10 goldens. → **VERIFIED (trivially true)**;
  plan fixed: explicit entry gate — PR #4 merged + each DoD scenario's exact CLI argv
  replays green before agent work builds on it.
- **MAJOR · CORS/proxy/streaming path missing** — Next :3000 + FastAPI :8000, but
  cloudflared exposes one origin. → accepted; plan now specifies same-origin Next.js
  proxy for AG-UI/SSE + cloudflared streaming test.
- **MAJOR · session/state under-specified** — session id origin, HITL resume binding,
  persona mutability, Responses server-side state retention. → accepted; plan now:
  UI-generated session uuid, persona frozen per session, `stateful=False` (client-side
  history), per-session kg_context with TTL cleanup.
- **MAJOR · MAX_TURNS_PER_SESSION insufficient as quota guard** — new sessions are
  free. → accepted; plan now: global daily token budget + concurrency semaphore +
  graceful 429 alongside the turn cap.
- **MAJOR · subprocess contract details missing** — argv/no-shell, cwd, timeout,
  output cap, exit-2 handling. → accepted; bullet added.
- **MAJOR · raw-Cypher tool is self-inflicted replay risk** — prompt obedience vs
  exact-match stub. → accepted; typed KG tools (`resolve_term(term_regex)`,
  `get_metric_context(metric_key)`) render canonical Cypher harness-side **from day
  one**; raw Cypher not exposed to the model.
- **MAJOR · scope infeasible in ~4 days** — recommends cutting dashboard +
  xlsx/parquet. → **partially accepted**: NOT cut (user-requested scope) but
  re-sequenced to after the four DoD conversations pass; explicitly the first thing to
  slip if the week compresses.
- **MAJOR · DoD partly subjective** — "visibly grows", "stays helpful". → accepted;
  mechanical assertions added (expected tool sequence, ≤1 retry per self-correction
  path, required trace attributes, chart data length == result rows).
- **MAJOR · KG panel assumes uniform envelope shapes** — `kg query` returns
  `result.records[]`; `metrics describe` a different object. → accepted; per-command
  adapters.
- **MINOR · parent-plan contradiction** — phase table says phase 2 = Karsten; the
  dependency text/diagram still put phase 2 in Phong's track. → accepted; fixed.

## Sources verified by Claude (2026-07-11)

- https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-openai-gpt-55.html
- https://aws.amazon.com/about-aws/whats-new/2025/12/amazon-bedrock-responses-api-from-openai/
- https://strandsagents.com/docs/user-guide/concepts/model-providers/openai-responses/
- https://docs.litellm.ai/docs/providers/bedrock_mantle (fallback path if needed)

## Unresolved questions

1. Exact bedrock-mantle path nuance: GPT-5.5 serves on `openai/v1/responses` on the
   bedrock-mantle endpoint (differs from the generic `v1/responses` responses
   endpoint) — confirm the final base_url string in the phase-5A smoke test.
2. Whether `OpenAIResponsesModel` `stateful=True` even works against bedrock-mantle —
   irrelevant if we ship `stateful=False`, revisit only if payloads get heavy.

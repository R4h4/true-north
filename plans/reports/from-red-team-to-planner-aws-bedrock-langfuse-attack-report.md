# Red-Team Attack Report: AWS Bedrock + Langfuse Plan (260711-1550)

**Scope reviewed:** `plans/260711-1550-parallel-aws-bedrock-langfuse/plan.md` + phases 01–06; research reports `researcher-260711-1550-{bedrock-agent-integration,langfuse-aws-bedrock,aws-deployment-shape}-report.md`.
**Method:** every infrastructure claim checked against AWS/Langfuse/Let's Encrypt primary sources (links inline). Repo facts grep-verified (`source/query/engine.py`, `source/data/TRAPS.md` exist; `st.session_state` and Elastic IP appear nowhere in the plan).

Overall: the parallelization/contract design is sound; the infrastructure layer is built on several unverified research claims, two of which fail on day 0.

---

## Findings (ranked)

### F1. CRITICAL — Model ID `global.anthropic.claude-sonnet-5-3` does not exist

**Evidence:** The [AWS model card for Claude Sonnet 5](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html) lists exact IDs: base `anthropic.claude-sonnet-5`, geo `us./eu.anthropic.claude-sonnet-5`, **global `global.anthropic.claude-sonnet-5`**. There is no `-3` suffix anywhere. The bedrock research report invented it (its own table is internally inconsistent: Haiku gets a real date-versioned ID, Sonnet 5 gets the fabricated short form), and it propagated into `plan.md` (Key Decisions + acceptance criteria), `phase-03` (architecture diagram), and `phase-05` (requirements, smoke test).
**Impact:** Phase 5A smoke test — the day-0 unblock for both tracks — fails with `ValidationException`. Team burns day 0 debugging IAM when the ID is wrong.
**Fix:** Global-replace with `global.anthropic.claude-sonnet-5`. Add a plan step: confirm via `aws bedrock list-inference-profiles --region ap-southeast-1 --type-equals SYSTEM_DEFINED` before writing any code. Treat every other numeric claim from that research report as unverified (see F10).

### F2. CRITICAL — New-account Bedrock quotas can be quasi-zero; Sonnet 5 burns output quota at 10x

**Evidence:** Widely reported that fresh/low-spend AWS accounts get drastically reduced Claude quotas — as low as [2 RPM / near-zero tokens-per-day](https://dev.to/aws-builders/ultra-low-bedrock-llm-rate-limits-for-new-aws-accounts-time-to-wake-up-your-inactive-aws-accounts-3no0), with [429 "too many tokens per day" on quasi-zero quotas](https://repost.aws/questions/QUmfeTj3cNRJGuelOAsFiFvg/bedrock-anthropic-claude-models-return-429-too-many-tokens-per-day-quasi-zero-quota-request-aws-support-escalation). Additionally, per [AWS token burndown docs](https://docs.aws.amazon.com/bedrock/latest/userguide/quotas-token-burndown.html), Claude Sonnet 5 output tokens burn quota at **10x** — and Sonnet 5's adaptive thinking is **always on and cannot be disabled** ([model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html)), so reasoning tokens bill and burn as output. An agent loop doing 3–5 converse calls per question multiplies this. Quota increase requests are deprioritized for accounts without existing traffic history.
**Impact:** Live demo throttling (429s) mid-pitch; the plan's only rate-related mitigation is a generic "retry on rate limit" in the research checklist. The plan's ~$0.01/query estimate also ignores reasoning tokens.
**Fix:** Day 0 (same session as use-case form): `aws service-quotas list-service-quotas --service-code bedrock` filtered for Sonnet 5 global profile; file increase requests immediately; generate steady light traffic all week (helps both quota history and demo warmup). Wire `BEDROCK_MODEL_ID` env fallback to Haiku 4.5 (already implied in phase 3 step 1 — make it a demo-day contingency, not just a dev convenience). Add exponential backoff on `ThrottlingException` inside the loop, and set a low reasoning effort via inference config for snappier demo turns.

### F3. MAJOR — Streamlit rerun model unaddressed: no `st.session_state` anywhere in the plan

**Evidence:** Phase 3 requires a "multi-turn tool-use loop" and "new chat = new Langfuse session id," and phase 6's demo beats depend on conversation continuity. Streamlit re-executes the entire script on **every** widget interaction ([docs](https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state)); without `st.session_state`, the messages list, Langfuse session id, and persona selection reset every turn — each question becomes turn 1. `grep -ri session_state plans/260711-1550-*` returns nothing.
**Impact:** The core "multi-turn" requirement silently doesn't work; discovered during phase 3 manual eval at best, on stage at worst. Secondary trap: switching the persona dropdown mid-chat triggers a rerun — decide explicitly whether it resets the conversation (it should: mixing personas in one message history is a governance-story bug).
**Fix:** Add to phase 3 step 5: `st.session_state.messages` for history, session id stored in session_state, `@st.cache_resource` for the boto3 and Langfuse clients (per-rerun client construction also re-reads env and re-establishes connections), persona change → explicit chat reset. Call `get_client().flush()` at the end of every `run_agent` before returning to Streamlit — the SDK batches in a background thread ([Langfuse FAQ on missing traces](https://langfuse.com/faq/all/missing-traces)); "reviewable live" traces (phase 6 requirement) need deterministic flushing, and a container kill/redeploy otherwise drops the last turns.

### F4. MAJOR — `nginx + certbot` on EC2 public DNS cannot work: Let's Encrypt bans `amazonaws.com`

**Evidence:** Let's Encrypt refuses issuance for `*.compute.amazonaws.com` hostnames — "forbidden by policy" ([community thread](https://community.letsencrypt.org/t/policy-forbids-issuing-name-for-aws/95246), [another](https://community.letsencrypt.org/t/unable-to-get-a-certificate-for-aws-ec2/106714)). The deployment research report's nginx config literally uses `server_name your-ec2-public-dns.compute.amazonaws.com` with a certbot step — that exact sequence fails. Plan.md and phase 5 step 9 inherit "nginx+certbot or Gradio share" without a domain.
**Impact:** Demo-day HTTPS path dead on arrival unless someone registers a domain; discovering this the morning of the demo means falling back to plain-HTTP `:8501` improvised.
**Fix:** Decide now: (a) buy a cheap domain day 0 and point an A record at the instance (pairs with F8), (b) Cloudflare Tunnel / Tailscale Funnel (no cert, no open ports, stable URL), or (c) accept plain HTTP on 8501 restricted by source IP. Note the Gradio `share=True` fallback is a Gradio feature — the plan's UI is Streamlit; "Gradio-style share link" is not a thing Streamlit has, so this fallback as written is also vapor.

### F5. MAJOR — Governance demo with zero authentication on the governance UI

**Evidence:** Phase 5 security group opens "8501 or 443 for demo" (publicly, per the research report's `0.0.0.0/0` rule). The Streamlit app's persona picker reads `contracts/personas.json` — static tokens `tok_ceo`, `tok_hcmc_manager`, `tok_analyst` — and injects the token for the selected persona. Identity is a client-side dropdown.
**Impact:** Two distinct problems. (1) Optics: the pitch is "governed BI — auth token → user → permissions," while any stranger on the venue Wi-Fi can open the URL and *be the CEO*. A judge who notices owns your Q&A. (2) Operational: an internet-exposed LLM chat endpoint with no auth lets scanners/pranksters burn your already-fragile Bedrock quota (F2) and pollute Langfuse traces during the demo.
**Fix:** Cheapest: restrict the SG to the venue/team IPs. Better for the story: a trivial login gate (nginx basic-auth or a Streamlit password from `st.secrets`) *in front of* the persona simulation, and one demo-script sentence: "in production the token comes from SSO; here we simulate three identities." Decide it in phase 1 when personas are frozen, not on demo day.

### F6. MAJOR — 16 GB memory budget doesn't close if Langfuse is self-hosted; research reports contradict the plan and each other

**Evidence / math (t3.xlarge, 16 GB):** Neo4j at the plan's 4 GB heap is really ~6–7 GB process (heap + page cache + JVM/native overhead). Self-hosted Langfuse v3+ is six containers — web, worker, Postgres, ClickHouse, Redis, MinIO — and ClickHouse alone wants 2–4 GB to not thrash; the stack realistically takes 4–6 GB. DuckDB aggregations over the full-scale multi-million-row dataset (phase 6 step 1 runs generation + ingest **on the box**) spike several GB per query. Plus Streamlit/agent, docker, OS ≈ 2 GB. Total: 15–18 GB on a 16 GB box → OOM-killer roulette, likely killing ClickHouse or Neo4j mid-demo. Contradictions: the deployment report recommends **8–10 GB Neo4j heap** on the same instance while the plan says "~4G", and the same report claims Langfuse fits in "~2–3GB (PostgreSQL + ClickHouse in a single container)" while the Langfuse report correctly lists 6 containers needing ≥16 GB for production. Its compose sketch is also wrong: Neo4j env keys like `server.memory.heap.max_size` are ignored by the image — must be `NEO4J_server_memory_heap_max__size` — and it omits worker/Redis/MinIO entirely.
**Impact:** The "fallback: self-host Langfuse on the demo EC2" (plan.md open question 1) is not a config toggle — it changes the instance size decision.
**Fix:** Make it explicit in phase 5: Langfuse Cloud ⇒ t3.xlarge OK (Neo4j 4 GB heap + 2 GB page cache, set both via correct `NEO4J_server_memory_*` env vars, add compose `mem_limit`s); self-host ⇒ t3.2xlarge, non-negotiable. Add a `docker stats` check to the 5B success criteria and rehearse the full-scale DuckDB queries under memory pressure before demo day.

### F7. MAJOR — Harness container must ship Karsten's entire stack; subprocess-per-tool-call latency ignored

**Evidence:** Tool dispatch is `subprocess: $GOVERNED_CLI_CMD --token ... graph|query` (phase 3). On EC2, compose runs one `harness` service (phase 5 architecture). Therefore `infra/harness.Dockerfile` (Phong's file) must bundle `governance/`, `source/`, `knowledge-graph/` code, the DuckDB data file, and Neo4j connectivity — i.e., the "harness image" is actually the whole-monorepo image. Nothing in phases 3/5 addresses this, and the suggested invocation `GOVERNED_CLI_CMD="uv run --project governance governed-cli"` (phase 4) does uv resolution/env-sync work on **every tool call** — multi-second cold starts appearing as slow tool spans in the very Langfuse traces you're showing judges. Volumes for the DuckDB file and `contracts/personas.json` are unspecified.
**Impact:** Phase 6's "integration is a config swap" claim breaks at the container boundary: the swap works on a laptop with a full checkout, then fails or crawls in Docker.
**Fix:** In phase 5: build the image from repo root, `uv sync --frozen` all workspace members at build time, and set `GOVERNED_CLI_CMD` to an installed console script (no `uv run` at call time). Add a success criterion: p50 tool-call subprocess overhead < 500 ms inside the container. Mount the DuckDB file read-only into the harness service.

### F8. MAJOR — "Instance stoppable overnight" with no Elastic IP: the URL changes every morning

**Evidence:** Phase 5 non-functional requirement: "instance stoppable overnight." Stop/start reassigns the public IPv4. No Elastic IP or DNS anywhere in the plan (grep confirms). Everything downstream binds to the address: SSH configs, nginx `server_name`, the TLS cert (F4), the demo URL in the script, and phase 6 step 6 explicitly dry-runs "from instance stop/start."
**Impact:** Each stop/start invalidates the shared URL; on demo morning that's a scramble.
**Fix:** Allocate an Elastic IP at launch (cost is the standard public-IPv4 charge, ~$0.005/h — noise) and, if F4 resolves to a real domain, point DNS at the EIP once. Add to 5B checklist.

### F9. MINOR — IAM policy contains phantom actions; resource ARNs need region wildcards for global routing

**Evidence:** Phase 5 step 2 grants `bedrock:Converse`/`bedrock:ConverseStream`. These are not the authorizing actions — the [Converse API reference](https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_Converse.html) states Converse requires **`bedrock:InvokeModel`** (ConverseStream → `bedrock:InvokeModelWithResponseStream`). The phantom actions are harmless but signal copy-from-research-without-verification. More materially: with a global profile, invocation must be allowed on the inference profile in the caller's account/region **and** on the foundation model in every possible destination region — so Resource needs `arn:aws:bedrock:ap-southeast-1:ACCOUNT:inference-profile/global.anthropic.claude-sonnet-5` plus `arn:aws:bedrock:*::foundation-model/*` (foundation-model ARNs have **no account id**; the bedrock research report's `arn:aws:bedrock:*:ACCOUNT_ID:foundation-model/*` matches nothing).
**Fix:** Policy = `InvokeModel` + `InvokeModelWithResponseStream` on the two resources above. Test from the instance role before Phase 6, not just from laptops (laptop IAM users may carry broader default policies and mask the gap).

### F10. MINOR — Pricing claims are inverted/unverifiable; don't put them in the pitch

**Evidence:** Plan.md: "global inference profile (+10%) is required." Per AWS docs/announcements surfaced in verification, for the 4.5+/5 generation the **global** profile bills the standard rate while **geo** profiles carry the ~10% regional premium — the plan has it backwards. The "intro $2/$10 until Aug 31" line traces only to the bedrock research report (whose model ID was fabricated, F1); the [model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html) defers all pricing to the pricing page.
**Impact:** Dollar impact ~zero at demo volume; credibility impact non-zero if a slide states wrong AWS pricing. Also every cost estimate ignores always-on reasoning tokens (F2).
**Fix:** Re-derive the per-query estimate from the [Bedrock pricing page](https://aws.amazon.com/bedrock/pricing/) after the first real traced queries (Langfuse gives you actual token counts — use them).

### F11. MINOR — Sonnet 5 always-on reasoning: loop must preserve `reasoningContent`; latency untested

**Evidence:** [Model card](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html): "adaptive thinking is always on and cannot be disabled; effort level is configurable." Converse responses will include reasoning content blocks; in a tool loop the assistant message must be echoed back **verbatim** (phase 3's design of appending `response["output"]["message"]` is correct — keep it that way; any "extract text only" refactor breaks tool use). Neither plan nor research reports mention reasoning at all.
**Impact:** Per-turn latency (thinking + up to 10 loop iterations) may make live demo turns feel slow; reasoning inflates output-token burndown (F2) and Langfuse usage numbers.
**Fix:** Add to phase 3 step 1: configure the lowest reasoning effort; measure end-to-end turn latency as part of the manual eval; include the golden-log fixture (already planned) *with* a reasoning block so the fixture test guards the echo-back invariant.

### F12. MINOR — Unpinned Langfuse self-host stack; Neo4j ingest not idempotent across stop/start

**Evidence:** Self-host path says "download official docker-compose.yml" / clone `langfuse/langfuse` HEAD; research sketches use `langfuse/langfuse:latest` and `clickhouse:latest`. Repo-HEAD compose files change without notice mid-week. Separately, phase 5's success criterion "stop/start survives (volumes persist Neo4j data)" combines badly with phase 6 step 1 "run KG ingest on the box": re-running ingest against a persistent volume duplicates nodes/relationships unless ingest uses `MERGE` + uniqueness constraints or wipes first — duplicated KG metadata silently changes demo answers ("define revenue" returns two definitions).
**Fix:** If self-hosting: commit a pinned compose file to `infra/` (specific `langfuse/langfuse` major-version tags, pinned ClickHouse/Postgres). Either way: add "ingest is idempotent (MERGE + constraints) or starts with `MATCH (n) DETACH DELETE n`" as a phase 4 conformance-adjacent requirement, and make the phase 6 dry-run include a second ingest run.

---

## What holds up under attack

(For risk calibration only.) Verified correct: ap-southeast-1 has no in-region/geo Claude Sonnet 5 — global profile is genuinely the only route ([model card regional table](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-anthropic-claude-sonnet-5.html)); Langfuse Cloud Hobby tier = 50k units/mo, 30-day retention, 2 users, and SDK v4 (March 2026 rewrite) is real and recommended for new projects ([pricing](https://langfuse.com/pricing)) — demo volume fits comfortably; no native Bedrock auto-instrumentation exists, so the manual `@observe` plan is right; mock-first contract strategy and the Haiku fallback are genuinely good de-risking.

## Recommended plan edits (priority order)

1. Fix the model ID everywhere; add `list-inference-profiles` verification step (F1).
2. Add quota check + increase request + throttling backoff + reasoning-effort config to Phase 5A/3 (F2, F11).
3. Add Streamlit state management + flush discipline to Phase 3 step 5 (F3).
4. Replace "certbot on EC2 DNS" with a real exposure decision (domain / tunnel / IP-restricted HTTP) + Elastic IP (F4, F8).
5. Put an auth gate or IP restriction in front of the public UI; script the "simulated identity" line (F5).
6. Make the Langfuse-hosting decision drive instance size; fix Neo4j env-var names; add mem limits (F6).
7. Specify harness image contents + CLI invocation without per-call `uv run` (F7).
8. Correct IAM actions/ARNs (F9); re-derive costs from observed tokens (F10); pin self-host images and require idempotent KG ingest (F12).

---

Status: DONE
Summary: 12 findings — 2 critical (fabricated Bedrock model ID that fails the day-0 smoke test; new-account quota + 10x output burndown with always-on reasoning threatening live-demo throttling), 6 major (Streamlit session state absent, certbot-on-amazonaws.com impossible, unauthenticated governance UI, 16 GB memory math fails under self-hosted Langfuse, harness-container packaging gap, no Elastic IP), 4 minor. Parallelization/contract design is solid; the infra layer inherited unverified research claims and needs the edits above before Phase 5A.
Concerns/Blockers: none blocking review; F1 and F2 must be resolved before any Phase 5A work is scheduled.

---
title: "Parallel two-track build: governed CLI contract, Bedrock harness, AWS + Langfuse"
description: "Contract-first split so Phong (harness) and Karsten (source/governance/knowledge-graph) build in parallel; Bedrock agent with Langfuse tracing, deployed on a single EC2 in ap-southeast-1"
status: pending
priority: P1
branch: "main"
tags: [parallel-work, contract, bedrock, langfuse, aws, neo4j]
blockedBy: [260711-1547-phongvu-demo-data]
blocks: []
created: "2026-07-11T08:53:15.161Z"
createdBy: "ck:plan"
source: skill
---

# Parallel two-track build: governed CLI contract, Bedrock harness, AWS + Langfuse

## Overview

Two people, four services, one integration point. The README already fixes ownership
(Phong: `harness/`; Karsten: `source/`, `governance/`, `knowledge-graph/`) and names the
single contract between them: a **governed CLI** (auth token → user → permissions) with two
surfaces — Cypher against the knowledge graph and data queries against the warehouse. That
CLI spec now exists — Karsten's [PR #2](https://github.com/R4h4/true-north/pull/2)
delivers `CONTRACT.md` v0.3 (the `tn` CLI) with golden examples; Phase 1 is reduced to
reviewing and ratifying it.

Strategy: **freeze the contract first (Phase 1), then never wait on each other again.**
Phong codes the harness against the stub `tn` CLI (canned responses, same goldens — Phase 2);
Karsten builds the real thing behind the same contract, proven equivalent by a shared
conformance test suite. Integration (Phase 6) is a stub-to-real replacement behind the
same `tn` entrypoint, not a merge scramble.

Requirements from the user: run on AWS, use AWS Bedrock for the LLM, use Langfuse for
observability.

## Key Decisions (research-backed, reports in `plans/reports/`)

| Decision | Choice | Why |
|---|---|---|
| LLM | **GPT-5.5 on Bedrock**, model ID `openai.gpt-5.5` (us-east-1/us-east-2 — verify region + exact ID day 0 with `aws bedrock list-foundation-models`) | Chosen 2026-07-11 over Claude Sonnet 5 for setup simplicity: **no Anthropic first-time-use form**, usable same-day. GA on Bedrock since June 2026, 272k context, strong agentic tool use. **Quota risk stays:** generic Bedrock on-demand quotas on fresh accounts — check Service Quotas + request increases day 0. Throttle/blocked fallback: gpt-oss (no form) or Claude Sonnet 5 (form takes days — see Phase 5 risk). |
| Bedrock API | **OpenAI SDK → Responses API** against the `bedrock-mantle` endpoint (`OPENAI_BASE_URL=https://bedrock-mantle.<region>.api.aws/openai/v1`, auth = Bedrock API key) | GPT-5.5 on Bedrock is served OpenAI-style, not via Converse. Tool loop = Responses-API function calling (`function_call` output items → `function_call_output` inputs). Bonus: the OpenAI SDK path unlocks Langfuse's native OpenAI instrumentation. |
| Tracing | **Langfuse Cloud free tier** (50k events/mo) + Python SDK v4 | 15-min setup vs ~45-min 6-container self-host stack. With the OpenAI SDK, try **`langfuse.openai` drop-in instrumentation first** (auto-captures generations + token usage); manual `@observe` wrapping remains for tool/agent spans and as fallback if the drop-in balks at the bedrock-mantle base URL. Cost config for `openai.gpt-5.5` still manual in the dashboard. Fallback: self-host on the demo EC2 if hackathon rules demand everything on AWS. |
| Neo4j | `neo4j:5-community` in Docker (local dev + on demo EC2) | AuraDB Free auto-pauses/deletes and caps size; Docker is identical Cypher, zero surprise. |
| Deployment | Single EC2 **t3.xlarge** (ap-southeast-1) + docker-compose + IAM instance role | Fits Neo4j + services (+ Langfuse if self-hosted); ~USD 5–7/day, ~50–65 for the week. ECS/App Runner rejected (App Runner in maintenance mode since Apr 2026). |
| Chat UI | Streamlit (with `st.session_state` for multi-turn), SSH tunnel during dev, **cloudflared quick tunnel** for demo day + a shared passphrase gate in the app | Let's Encrypt refuses `*.compute.amazonaws.com` hostnames, so certbot-on-EC2 is a dead end without a domain; a quick tunnel gives a free HTTPS URL. The passphrase gate stops strangers from playing CEO (`tok-exec-mai`) and burning Bedrock quota — embarrassing for a governance demo. |

## Parallel-Work Rules (the actual answer to "don't mess up each other")

1. **Directory ownership is absolute.** Phong: `harness/`, `infra/`. Karsten: `source/`,
   `governance/`, `knowledge-graph/`. Nobody edits the other's directories — ask instead.
2. **Joint-change-controlled paths** (change only via PR approved by the other person):
   `CONTRACT.md`, `contracts/` (goldens + conformance tests — contract rule: goldens
   update in the same PR as any contract change), root `README.md`, root `pyproject.toml`.
3. **Git workflow:** small commits straight to `main` inside your own directories,
   `git pull --rebase` before every push. Branches + PR only for joint-controlled paths
   or anything cross-cutting.
4. **`uv.lock` conflicts:** never hand-merge; on conflict run `uv lock` and commit the result.
5. **Contract changes after the freeze** are versioned in the spec's changelog section and
   announced in chat; the conformance suite is updated in the same PR.
6. **No cross-fence code imports.** Harness code (and any fixture tooling) must not
   import `source/`/`governance/`/`knowledge-graph/` Python modules — only the `tn` CLI
   and generated data files are stable surfaces; module internals get refactored
   mid-week.

## Phases

| Phase | Name | Owner | Status |
|-------|------|-------|--------|
| 1 | [Interface Contract & Workfences](./phase-01-interface-contract-workfences.md) | Joint (day 0) | Pending |
| 2 | [Stub CLI Fixtures & Conformance Tests](./phase-02-mock-governed-cli-conformance-tests.md) | Karsten (PR #4) | Pending |
| 3 | [Harness Agent: GPT-5.5 + Langfuse + Charts](./phase-03-harness-agent-bedrock-langfuse.md) | Phong | Pending |
| 4 | [Karsten Track: Semantic Layer & Governed Services](./phase-04-karsten-track-semantic-layer-governed-services.md) | Karsten | Pending |
| 5 | [AWS Environment & Deployment](./phase-05-aws-environment-deployment.md) | Phong | Pending |
| 6 | [Integration & Demo](./phase-06-integration-demo.md) | Joint | Pending |

## Dependencies

- Phase 1 blocks everything (it IS the parallelization enabler; timebox: half a day).
- Phong track: 1 → 2 → 3; Karsten track: 1 → 4. **2+3 run in parallel with 4.**
- Phase 5 milestone A (Bedrock access, Langfuse keys, local Neo4j) happens day 0–1 in
  parallel with Phase 1; milestone B (EC2 deploy) any time before Phase 6.
- **Hard mid-build gate:** the day Karsten's real CLI first passes conformance, run a
  1-hour harness↔real-CLI smoke together. Phase 6 must not be the first real contact.
- Phase 6 needs 3, 4, 5 done **plus** the generated dataset from plan
  `260711-1547-phongvu-demo-data` (cross-plan `blockedBy`; only Phase 6 and late Phase 4
  testing are hard-blocked by it — everything else proceeds on tiny/small scale data).

```
Day 0        Day 1-4                     Day 5      Day 6
Phase 1 ──┬── Phase 2 ── Phase 3 ────────┬─ Phase 5B ─ Phase 6
(joint)   │   (Phong)    (Phong)         │  (Phong)    (joint)
          └── Phase 4 (Karsten) ─────────┘
Phase 5A (Phong, day 0-1, parallel)
[demo-data plan runs in parallel, feeds Phase 4 testing + Phase 6]
```

## Acceptance Criteria

- [ ] `CONTRACT.md` v0.3 ratified and merged (PR #2) with Phong's divergence positions recorded.
- [ ] Conformance suite passes against the stub (Phase 2) and later against the real CLI (Phase 4) unchanged.
- [ ] Harness answers trap questions end-to-end through Bedrock (GPT-5.5 via bedrock-mantle) with every agent step visible as a nested Langfuse trace (session + persona tagged).
- [ ] Whole stack runs on the EC2 instance via docker-compose; Bedrock reached with a **scoped Bedrock API key** (bedrock-only permissions, no general AWS credentials on the box).
- [ ] Demo: at least 2 personas give different answers to the same question (row-level security visible), and one "metric exists but you lack access" answer sourced from KG permission metadata.
- [ ] No cross-directory edits without the owner's sign-off during the whole build (spot-check via `git log --stat`).

## Resolved Decisions (validated with Phong, 2026-07-11)

1. **Langfuse Cloud** — free tier; EC2 stays t3.xlarge; self-host remains the documented fallback only if organizers object.
2. **Timeline ~1 week** — day-numbered schedule stands as written.
3. **Phong's personal/company AWS account** — he controls IAM; Bedrock quota checks + increase requests submitted immediately (day 0, before anything else).
4. "Karsen" = Karsten (README spelling) — assumed, not re-confirmed.
5. **Warehouse surface is a metrics DSL, not raw SQL** (Phong, 2026-07-11) — exposing SQL
   directly to the warehouse is dangerous and defeats the governance story. The agent
   requests governed metrics (structured tool args); the semantic layer owns all SQL.
   Confirmed as contractual in CONTRACT.md v0.3 ("no raw-SQL surface for any role").
6. **Contract v0.3 (PR #2, Karsten) supersedes the Phase-1 draft** (reconciled
   2026-07-11): CLI is `tn` (`uv run tn`, stub-first behind the same entrypoint); contract
   lives at root `CONTRACT.md` + 10 goldens in `contracts/examples/`; flag-based DSL
   (`--metric/--group-by/--grain/--filter/--start/--end`); typed permission disclosures
   replace free-prose notices; 10 error codes (existence vs permission distinguishable,
   `candidates`/`did_you_mean` self-correction details); exit codes 0/1/2; 4 personas
   (adds marketing-ops; row filter = region South); KG schema + invariants + canonical
   Cypher are contract (§4), served by `tn kg schema`; uv workspace members
   pre-registered. Phong's mock-CLI build is downgraded to conformance runner + replay
   fixtures (phase 2). Stub ownership since resolved: Karsten ships it (PR #4, with
   conformance suite + agent-dev fixtures + docs/USING-TN.md). Still open: warning-code
   set (closed or extensible).
7. **GPT-5.5 replaces Claude Sonnet 5** (Phong, 2026-07-11) — simpler setup: no Anthropic
   first-time-use form, GA on Bedrock since June 2026. Consequences absorbed in phases
   3/5: OpenAI SDK + Responses API against the bedrock-mantle endpoint (not boto3
   Converse), Bedrock API key auth, model region us-east-1/us-east-2 (EC2 stays in
   ap-southeast-1 — cross-region API latency is fine for a demo), Langfuse native OpenAI
   instrumentation replaces most manual wrapping. Claude notes in the Bedrock research
   report are retained for the fallback path only.

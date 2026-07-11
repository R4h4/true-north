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
CLI spec does not exist yet, and it is the only thing that can block parallel work.

Strategy: **freeze the contract first (Phase 1), then never wait on each other again.**
Phong codes the harness against a mock governed CLI (Phase 2) that implements the contract;
Karsten builds the real thing behind the same contract, proven equivalent by a shared
conformance test suite. Integration (Phase 6) is a config swap, not a merge scramble.

Requirements from the user: run on AWS, use AWS Bedrock for the LLM, use Langfuse for
observability.

## Key Decisions (research-backed, reports in `plans/reports/`)

| Decision | Choice | Why |
|---|---|---|
| LLM | Claude Sonnet 5 via Bedrock global inference profile `global.anthropic.claude-sonnet-5` — **verify exact ID day 0** with `aws bedrock list-foundation-models` (red team caught a fabricated ID in the research report) | Best cost/latency/tool-use balance (~$3/$15 per MTok); ap-southeast-1 has no in-region Claude, so the global profile is mandatory. ~$0.01/query. **Quota risk:** fresh accounts can have near-zero Claude quotas and Sonnet 5's always-on reasoning burns output quota — check Service Quotas + request increases day 0; Haiku 4.5 is the throttle fallback. |
| Bedrock API | boto3 `bedrock-runtime` **Converse API** | Tool use requires Converse (not legacy InvokeModel); no framework overhead; best-documented path. Strands/Anthropic-SDK rejected as overkill/indirect for a 2-tool loop. Sonnet 5 emits `reasoningContent` blocks that must be echoed back verbatim in the tool loop. |
| Tracing | **Langfuse Cloud free tier** (50k events/mo) + Python SDK v4 | 15-min setup vs ~45-min 6-container self-host stack. No native Bedrock instrumentation exists — manual `@observe` wrapping; token usage from `response["usage"]`, cost config manual. Fallback: self-host docker-compose on the demo EC2 if hackathon rules demand everything on AWS. **← confirm at validation** |
| Neo4j | `neo4j:5-community` in Docker (local dev + on demo EC2) | AuraDB Free auto-pauses/deletes and caps size; Docker is identical Cypher, zero surprise. |
| Deployment | Single EC2 **t3.xlarge** (ap-southeast-1) + docker-compose + IAM instance role | Fits Neo4j + services (+ Langfuse if self-hosted); ~USD 5–7/day, ~50–65 for the week. ECS/App Runner rejected (App Runner in maintenance mode since Apr 2026). |
| Chat UI | Streamlit (with `st.session_state` for multi-turn), SSH tunnel during dev, **cloudflared quick tunnel** for demo day + a shared passphrase gate in the app | Let's Encrypt refuses `*.compute.amazonaws.com` hostnames, so certbot-on-EC2 is a dead end without a domain; a quick tunnel gives a free HTTPS URL. The passphrase gate stops strangers from playing CEO (`tok_ceo`) and burning Bedrock quota — embarrassing for a governance demo. |

## Parallel-Work Rules (the actual answer to "don't mess up each other")

1. **Directory ownership is absolute.** Phong: `harness/`, `infra/`. Karsten: `source/`,
   `governance/`, `knowledge-graph/`. Nobody edits the other's directories — ask instead.
2. **Joint-change-controlled paths** (change only via PR approved by the other person):
   `docs/governed-cli-contract.md`, `contracts/` (schemas, personas, conformance tests),
   root `README.md`, root `pyproject.toml`.
3. **Git workflow:** small commits straight to `main` inside your own directories,
   `git pull --rebase` before every push. Branches + PR only for joint-controlled paths
   or anything cross-cutting.
4. **`uv.lock` conflicts:** never hand-merge; on conflict run `uv lock` and commit the result.
5. **Contract changes after the freeze** are versioned in the spec's changelog section and
   announced in chat; the conformance suite is updated in the same PR.
6. **No cross-fence code imports.** The mock CLI reads `source/data/parquet/` files
   directly (generated *data* is a stable contract — schema.py is the single source of
   truth); it must NOT import `source/` Python modules, whose internals Karsten will
   refactor mid-week.

## Phases

| Phase | Name | Owner | Status |
|-------|------|-------|--------|
| 1 | [Interface Contract & Workfences](./phase-01-interface-contract-workfences.md) | Joint (day 0) | Pending |
| 2 | [Mock Governed CLI & Conformance Tests](./phase-02-mock-governed-cli-conformance-tests.md) | Phong | Pending |
| 3 | [Harness Agent: Bedrock + Langfuse](./phase-03-harness-agent-bedrock-langfuse.md) | Phong | Pending |
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

- [ ] `docs/governed-cli-contract.md` frozen and signed off by both owners; personas fixture committed.
- [ ] Conformance suite passes against the mock (Phase 2) and later against the real CLI (Phase 4) unchanged.
- [ ] Harness answers trap questions end-to-end through Bedrock (Sonnet 5 global profile) with every agent step visible as a nested Langfuse trace (session + persona tagged).
- [ ] Whole stack runs on the EC2 instance via docker-compose; Bedrock reached via instance IAM role (no long-lived keys on the box).
- [ ] Demo: at least 2 personas give different answers to the same question (row-level security visible), and one "metric exists but you lack access" answer sourced from KG permission metadata.
- [ ] No cross-directory edits without the owner's sign-off during the whole build (spot-check via `git log --stat`).

## Resolved Decisions (validated with Phong, 2026-07-11)

1. **Langfuse Cloud** — free tier; EC2 stays t3.xlarge; self-host remains the documented fallback only if organizers object.
2. **Timeline ~1 week** — day-numbered schedule stands as written.
3. **Phong's personal/company AWS account** — he controls IAM; Anthropic use-case form + Sonnet 5 quota-increase requests submitted immediately (day 0, before anything else).
4. "Karsen" = Karsten (README spelling) — assumed, not re-confirmed.

---
phase: 5
title: "AWS Environment & Deployment"
status: pending
priority: P1
dependencies: [1]
---

# Phase 5: AWS Environment & Deployment

## Overview

Two milestones with very different urgency. **5A (day 0–1):** unblock both tracks —
Bedrock access, Langfuse keys, local Neo4j. **5B (before demo):** put the whole stack on
one EC2 instance so the project demonstrably "runs on AWS".

## Requirements

- Functional: GPT-5.5 callable via the bedrock-mantle Responses endpoint
  (`openai.gpt-5.5` — confirm exact ID and serving region, us-east-1 vs us-east-2,
  against `aws bedrock list-foundation-models` before hardcoding anything); Langfuse
  project receiving traces; demo EC2 serving the Streamlit chat with all services up.
- Non-functional: the only AWS credential on the EC2 box is a **Bedrock API key scoped to
  bedrock invocation** (bedrock-mantle takes bearer-style auth, so a pure instance-role
  setup doesn't apply; a scoped key is the pragmatic equivalent); daily cost ~USD 5–7
  (t3.xlarge on-demand, ap-southeast-1); instance stoppable overnight with a stable
  address (Elastic IP — small hourly IPv4 charge, worth it vs URL/SSH-config churn).

## Architecture

```
EC2 t3.xlarge (ap-southeast-1, Ubuntu 22.04, Elastic IP,
               Bedrock API key in env — scoped to bedrock invocation only)
  docker-compose (infra/docker-compose.yml):
    neo4j:5-community          (7474/7687, volume, heap capped ~4G)
    harness                    (Streamlit :8501; calls `uv run tn` — real CLI by then)
    [langfuse stack]           (only if self-host decision — 6 containers: web, worker,
                                postgres, clickhouse, redis, minio)
  security group: 22 (team IPs only); nothing else inbound
  UI exposure: SSH tunnel during dev; cloudflared quick tunnel (outbound-only, free HTTPS
  URL) on demo day — certbot/Let's Encrypt on *.compute.amazonaws.com is banned by LE
  policy, so nginx+certbot needs a real domain we don't want to manage. App itself gated
  by DEMO_PASSPHRASE (phase 3).
```

- Bedrock note: GPT-5.5 serves from **us-east-1/us-east-2** via the bedrock-mantle
  endpoint — the EC2 stays in ap-southeast-1 and calls cross-region (~200ms extra API
  latency, irrelevant next to model inference time). Data goes to a US region — fine for
  synthetic demo data.
- Model access: **no first-time-use form for OpenAI models** (that requirement is
  Anthropic-specific) — standard simplified access; enable in the console if prompted.
- Dev-time Bedrock (before 5B): each laptop gets the same scoped Bedrock API key (or its
  own — they're cheap to mint and revoke).

## Related Code Files

- Create: `infra/docker-compose.yml`, `infra/harness.Dockerfile`,
  `infra/bedrock-iam-policy.json` (machine files only), and `docs/deployment.md`
  (run/deploy instructions — markdown lives in docs/).
- Modify: `harness/.env.example` (document EC2 vs laptop differences).

## Implementation Steps

**5A — enablement (day 0–1, ~2h):**
1. AWS account ready; verify GPT-5.5 availability and capture the exact model ID +
   serving region: `aws bedrock list-foundation-models --region us-east-1` (and
   us-east-2). No use-case form needed for OpenAI models. **Optional insurance:** submit
   the Anthropic form anyway (5 min, free) so Claude is a live fallback later in the week.
2. Mint a **Bedrock API key** (Bedrock console → API keys) backed by an identity whose
   policy is bedrock-invocation-only; set `OPENAI_API_KEY` +
   `OPENAI_BASE_URL=https://bedrock-mantle.<region>.api.aws/openai/v1` on both laptops.
3. Smoke test: one `client.responses.create(model="openai.gpt-5.5", ...)` from Python via
   the OpenAI SDK, including one function-tool round-trip (the item format is the most
   likely early bug). **Same session:** check Service Quotas for OpenAI-model RPM/TPM —
   fresh-account quotas can sit low; request increases immediately (they take days).
   Confirm whether `previous_response_id` works on bedrock-mantle while you're there.
4. Langfuse: per the validation decision — Cloud: create org/project, issue keys to both;
   self-host: defer to 5B, use Cloud keys meanwhile (traces are throwaway).
5. Local Neo4j one-liner documented for Karsten:
   `docker run -p 7474:7474 -p 7687:7687 -e NEO4J_AUTH=neo4j/truenorth neo4j:5-community`.

**5B — demo deployment (any time after Phase 3 works, ≤ half day):**
6. Launch t3.xlarge + instance role + **Elastic IP**; install docker + compose plugin.
   If the Langfuse self-host decision landed: go t3.2xlarge instead — 16 GB does not
   credibly fit Neo4j (~6–7 GB real footprint) + 6 Langfuse containers + full-scale
   DuckDB spikes + Streamlit.
7. Write `infra/docker-compose.yml`: **pin image tags** (neo4j:5.x.y, langfuse versions);
   Neo4j heap capped via the current env names (`NEO4J_server_memory_heap_max__size` —
   the old `dbms.*` names are silently ignored by the 5.x image); Langfuse secrets
   (NEXTAUTH_SECRET/SALT/ENCRYPTION_KEY) via `openssl rand -hex 32` if self-hosting.
8. Harness image: bake the repo + a pre-built venv and invoke the governed CLI through a
   direct entrypoint — per-call `uv run` cold starts would show up as fat multi-second
   tool spans in the very Langfuse traces we demo. The image must include `source/` code
   and generated parquet (the CLI and data live behind the same container boundary).
9. Deploy = `git pull && docker compose up -d --build`; run data generation + idempotent
   KG ingest on the box; run conformance suite there.
10. Expose UI (SSH tunnel for rehearsal, cloudflared quick tunnel for demo day); write
    `docs/deployment.md`.

## Success Criteria

- [ ] 5A: both laptops can call GPT-5.5 via the Responses API (incl. one function-tool
  round-trip) and see the trace in Langfuse — **by end of day 1**; quotas checked and
  increases requested the same day.
- [ ] 5B: fresh `docker compose up -d` on the EC2 brings up everything; chat answers a trap question end-to-end from a phone browser.
- [ ] The only AWS credential on the box is the scoped Bedrock API key env var; no
  `~/.aws/credentials` file exists.
- [ ] Stop/start of the instance survives (volumes persist Neo4j + Langfuse data).

## Risk Assessment

- **bedrock-mantle surprises** (endpoint quirks, missing Responses features like
  `previous_response_id`, SDK version sensitivity) → GPT-5.5 on Bedrock is only ~5 weeks
  GA; smoke-test the full tool round-trip day 0 and pin the openai SDK version. Fallbacks
  in order: gpt-oss on Bedrock (no form, boto3 Converse) or Claude Sonnet 5 (needs the
  Anthropic form — submitted day 0 as insurance).
- **t3.xlarge memory pressure with self-hosted Langfuse + Neo4j + full-scale DuckDB** →
  cap Neo4j heap; if tight, bump to t3.2xlarge (still ~USD 13/day) rather than debugging OOM.
- **Global inference data-residency objection from organizers** → only alternative is
  running compute in us-east-1 instead; decide only if actually challenged.

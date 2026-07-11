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

- Functional: Bedrock Converse callable with the Sonnet 5 global profile
  (`global.anthropic.claude-sonnet-5` — confirm the exact ID against
  `aws bedrock list-foundation-models` output before hardcoding anything); Langfuse
  project receiving traces; demo EC2 serving the Streamlit chat with all services up.
- Non-functional: no long-lived AWS keys on the EC2 box (instance role); daily cost ~USD
  5–7 (t3.xlarge on-demand, ap-southeast-1); instance stoppable overnight with a stable
  address (Elastic IP — small hourly IPv4 charge, worth it vs URL/SSH-config churn).

## Architecture

```
EC2 t3.xlarge (ap-southeast-1, Ubuntu 22.04, Elastic IP,
               IAM instance role: bedrock:InvokeModel[WithResponseStream])
  docker-compose (infra/docker-compose.yml):
    neo4j:5-community          (7474/7687, volume, heap capped ~4G)
    harness                    (Streamlit :8501; GOVERNED_CLI_CMD → real CLI)
    [langfuse stack]           (only if self-host decision — 6 containers: web, worker,
                                postgres, clickhouse, redis, minio)
  security group: 22 (team IPs only); nothing else inbound
  UI exposure: SSH tunnel during dev; cloudflared quick tunnel (outbound-only, free HTTPS
  URL) on demo day — certbot/Let's Encrypt on *.compute.amazonaws.com is banned by LE
  policy, so nginx+certbot needs a real domain we don't want to manage. App itself gated
  by DEMO_PASSPHRASE (phase 3).
```

- Bedrock note: ap-southeast-1 has **no in-region Claude**; global inference profile is
  mandatory (research reports disagreed on whether global carries a premium — red team
  says global bills standard rate; check the pricing page before quoting numbers to
  anyone). Data transits other regions — fine for synthetic demo data.
- Model access: one-time Anthropic use-case submission on the AWS account (Bedrock console
  → Model access), then models are auto-enabled.
- Dev-time Bedrock (before 5B): personal IAM user/SSO profile on each laptop with the same
  policy.

## Related Code Files

- Create: `infra/docker-compose.yml`, `infra/harness.Dockerfile`,
  `infra/bedrock-iam-policy.json` (machine files only), and `docs/deployment.md`
  (run/deploy instructions — markdown lives in docs/).
- Modify: `harness/.env.example` (document EC2 vs laptop differences).

## Implementation Steps

**5A — enablement (day 0–1, ~2h):**
1. AWS account ready; submit Anthropic use-case form; verify model list AND capture the
   exact Sonnet 5 global-profile ID:
   `aws bedrock list-foundation-models --region ap-southeast-1` +
   `aws bedrock list-inference-profiles --region ap-southeast-1`.
2. IAM policy: the authorizing action for Converse is **`bedrock:InvokeModel`** (+
   `bedrock:InvokeModelWithResponseStream` for streaming) — there is no separate
   `bedrock:Converse` action. Resources: `arn:aws:bedrock:*::foundation-model/*` (no
   account id) **and** `arn:aws:bedrock:*:ACCOUNT_ID:inference-profile/*` (region
   wildcard — global routing invokes in other regions). Attach to both laptops'
   identities.
3. Smoke test: one `converse()` call with the captured profile ID from Python.
   **Same session:** check Service Quotas for Sonnet 5 RPM/TPM — fresh accounts can sit
   near zero and Sonnet 5 reasoning tokens burn output quota at speed. Request increases
   immediately (they take days and are deprioritized for no-traffic accounts); rehearse
   with Haiku 4.5 as the throttle fallback either way.
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

- [ ] 5A: both laptops can call Sonnet 5 via Converse and see the trace in Langfuse — **by end of day 1**; Sonnet 5 quota checked and increase requested the same day.
- [ ] 5B: fresh `docker compose up -d` on the EC2 brings up everything; chat answers a trap question end-to-end from a phone browser.
- [ ] `aws sts get-caller-identity` on the box shows the instance role; no `~/.aws/credentials` file exists.
- [ ] Stop/start of the instance survives (volumes persist Neo4j + Langfuse data).

## Risk Assessment

- **Anthropic use-case approval delays** → submit day 0, first thing; while waiting, build
  Phase 2/3 scaffolding (loop testable with a fake converse response fixture).
- **t3.xlarge memory pressure with self-hosted Langfuse + Neo4j + full-scale DuckDB** →
  cap Neo4j heap; if tight, bump to t3.2xlarge (still ~USD 13/day) rather than debugging OOM.
- **Global inference data-residency objection from organizers** → only alternative is
  running compute in us-east-1 instead; decide only if actually challenged.

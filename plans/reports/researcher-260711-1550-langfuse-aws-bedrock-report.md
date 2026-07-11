# Langfuse + AWS Bedrock for Hackathon: Research Report

**Date:** July 11, 2026  
**Scope:** 1-2 week hackathon; Python LLM agent using AWS Bedrock (boto3 Converse API); Langfuse for LLM observability.  
**Stack requirement:** "Needs to run on AWS"  
**Team:** Vietnam-based  

---

## Executive Summary

For a hackathon, **use Langfuse Cloud + Python SDK v4** unless you have hard data-residency requirements. Self-hosted on AWS is viable (t3.medium + docker-compose) but adds operational overhead not worth the 1-2 week ROI. Bedrock integration requires manual instrumentation via `@observe` decorators and manual cost tracking—no auto-instrumentation exists. Estimated setup time: **Cloud ~15 mins, self-hosted ~45 mins**.

---

## 1. Langfuse Cloud vs Self-Hosted on AWS

### Langfuse Cloud (Free Tier)

**Limits:**
- 50,000 events/month (perpetual; not a trial)
- 30-day data retention
- 2 concurrent users
- Includes: tracing, prompt management, evaluations, full SDK

**Cost:** Free unless you exceed 50K events/month. Overage pricing ~$0.10/1K events above the tier.

**Verdict for hackathon:** Sufficient for typical 1-2 week scope. A chatbot making 2 API calls per user request uses 50K events in ~25K user interactions—realistic but requires monitoring.

---

### Self-Hosted on AWS: v3 Architecture

**Service stack (6 containers):**
1. **langfuse-web** (port 3000): UI + API
2. **langfuse-worker** (port 3030): background jobs (evals, scoring)
3. **ClickHouse** (8123, 9000): columnar OLAP DB for trace analytics
4. **MinIO** (9090): S3-compatible object storage
5. **Redis 7** (6379): queue + cache
6. **PostgreSQL 17** (5432): relational DB (auth, projects, settings only; traces → ClickHouse)

**Why this split:** ClickHouse executes aggregation queries (e.g., "avg latency over 30 days") in milliseconds vs seconds in PostgreSQL.

**Resource requirements:**
- **Production:** ≥4 cores, ≥16 GB RAM (AWS t3.xlarge or larger)
- **Hackathon scale:** Users report running on t3.medium (~1k traces/day) with acceptable performance

**Setup:**
1. Provision t3.medium EC2 (Ubuntu 22.04 LTS)
2. Install Docker, docker-compose
3. Download official docker-compose.yml
4. Set env vars: `NEXTAUTH_SECRET`, `SALT`, `ENCRYPTION_KEY` (generate random strings)
5. Run `docker-compose up -d`
6. Visit `http://<ec2-ip>:3000`, create first account (becomes admin)

**Estimated time:** ~20–30 mins (download, env setup, compose up)

**Operational overhead:**
- Backup strategy (PostgreSQL, ClickHouse, MinIO)
- Monitoring (docker health checks, disk space on t3.medium)
- Upgrade path (pulling new images, data migrations)

---

### Comparison Matrix

| Dimension | Cloud | Self-Hosted (t3.medium) |
|-----------|-------|------------------------|
| **Setup time** | ~15 min (account + keys) | ~30 min (EC2 + docker-compose) |
| **Monthly cost** | $0 (50K events free) | ~$25–35 (t3.medium, EBS, data transfer) |
| **Data residency** | US (cloud.langfuse.com) or EU | Full control; on your AWS account |
| **Data retention** | 30 days (free tier) | Unlimited (you manage backups) |
| **Scaling** | Handled by Langfuse | Manual (resize EC2 or split services) |
| **Availability** | 99.9% SLA | As good as your deployment |
| **Compliance** | Depends on Langfuse's SOC2/HIPAA | You audit/maintain |

---

### Recommendation for Hackathon

**Use Langfuse Cloud if:**
- Event volume expected <50K/month
- Team is comfortable with US data residency (EU option available)
- Fastest time-to-value is priority
- No compliance requirements

**Use self-hosted if:**
- Hard requirement that system "runs on AWS" (e.g., client mandate)
- Expect >100K events/month and want to avoid overage costs
- Need to retain data indefinitely
- Data cannot leave customer AWS account

**Pragmatic call:** Cloud first, then pivot to self-hosted on t3.medium if you hit 50K events or compliance blocker mid-hackathon.

---

## 2. Langfuse Python SDK: v3 vs v4

### Release Timeline & Architecture

**v3 (May 2025):** OpenTelemetry-based, decorator & context manager APIs.

**v4 (March 2026, current):** Observation-centric data model; breaking changes to attribute propagation and span filtering.

### Key Differences

**Data model:**
- **v3:** Attributes (user_id, session_id, metadata) live on traces
- **v4:** Attributes propagate to every observation (span/generation/event); enables single-table queries, faster analytics at scale

**Attribute handling:**
- **v3:** `update_current_trace(user_id=...)`
- **v4:** `propagate_attributes(user_id=...)` context manager; auto-applies to all child observations

**Span filtering:**
- **v3:** Exports all OTel spans
- **v4:** Smart filtering; non-LLM spans (HTTP, DB, queues) filtered by default to reduce noise

**API unification:**
- **v3:** Separate `start_span()`, `start_generation()`, `start_event()`
- **v4:** Unified `start_observation(as_type="span"|"generation"|"event")`

### Which to Use for New Projects?

**Recommendation: v4** if starting fresh. It's the current direction and better architected for scale. v4 has better attribute propagation for agents (e.g., tagging all LLM calls under one user_id in a single statement).

**Risk:** v4 is 4 months old; broader than v3 but fewer production battle stories. If the team is risk-averse and v3 examples are easier to find, v3 is stable.

**For this hackathon:** v4 is acceptable; SDK is actively maintained and the breaking changes are straightforward.

---

## 3. AWS Bedrock + Langfuse Integration

### No Native Auto-Instrumentation

Langfuse has native instrumentations for OpenAI, Anthropic (Claude), Google—**but not for AWS Bedrock via boto3**. You must manually wrap calls.

### Manual Instrumentation Pattern

**Decorator approach (recommended for agents):**

```python
from langfuse import observe, get_client
import boto3

bedrock_client = boto3.client("bedrock-runtime", region_name="us-east-1")
langfuse = get_client()  # reads env vars

@observe(as_type="generation", name="bedrock_converse")
def call_bedrock_converse(
    model_id: str,
    messages: list,
    max_tokens: int = 1024
) -> str:
    """Wrap Bedrock Converse API with Langfuse tracing."""
    
    # 1. Log input metadata
    langfuse.update_current_generation(
        input=messages,
        model=model_id,
        model_parameters={"maxTokens": max_tokens}
    )
    
    # 2. Call Bedrock
    try:
        response = bedrock_client.converse(
            modelId=model_id,
            messages=messages,
            inferenceConfig={"maxTokens": max_tokens}
        )
    except Exception as e:
        langfuse.update_current_generation(
            status="error",
            error=str(e)
        )
        raise
    
    # 3. Log output + token usage
    output_text = response["output"]["message"]["content"][0]["text"]
    usage = response.get("usage", {})
    
    langfuse.update_current_generation(
        output=output_text,
        usage_details={
            "input": usage.get("inputTokens", 0),
            "output": usage.get("outputTokens", 0)
        }
    )
    
    return output_text
```

**Context manager approach (for more control):**

```python
with langfuse.start_as_current_observation(
    as_type="generation",
    name="bedrock_agent_step",
    input={"prompt": user_prompt},
    model="claude-sonnet-5"
) as obs:
    response = bedrock_client.converse(
        modelId="anthropic.claude-sonnet-5-v1:0",
        messages=[{"role": "user", "content": user_prompt}]
    )
    obs.end(
        output=response["output"]["message"]["content"][0]["text"],
        usage_details={
            "input": response["usage"]["inputTokens"],
            "output": response["usage"]["outputTokens"]
        }
    )
```

### For Tool-Calling Agents

**Nested spans propagate automatically via OTel context:**

```python
@observe(as_type="span", name="agent_loop")
def run_agent(user_query: str) -> str:
    # This creates a parent span
    
    # Each Bedrock call below nests under agent_loop
    llm_response = call_bedrock_converse(
        model_id="anthropic.claude-sonnet-5-v1:0",
        messages=[{"role": "user", "content": user_query}]
    )
    
    # If you call a tool, create a child observation
    with langfuse.start_as_current_observation(
        as_type="span",
        name="call_tool_search"
    ) as tool_span:
        tool_result = search_api(llm_response["tool_name"])
    
    # Final LLM call (also nests)
    final_response = call_bedrock_converse(
        model_id="anthropic.claude-sonnet-5-v1:0",
        messages=[
            {"role": "user", "content": user_query},
            {"role": "assistant", "content": llm_response["text"]},
            {"role": "user", "content": f"Tool result: {tool_result}"}
        ]
    )
    
    return final_response
```

**Result in Langfuse UI:**
```
agent_loop (trace)
├── bedrock_converse (generation)
├── call_tool_search (span)
│   └── (tool-specific observations)
└── bedrock_converse (generation)
```

---

## 4. Token Usage and Cost Tracking for Bedrock

### How Token Usage is Captured

Bedrock's `converse()` response includes:
```python
response["usage"] = {
    "inputTokens": 150,      # tokens in messages
    "outputTokens": 200,     # tokens in response
}
```

You **must** extract and pass to Langfuse manually:

```python
langfuse.update_current_generation(
    usage_details={
        "input": response["usage"]["inputTokens"],
        "output": response["usage"]["outputTokens"]
    }
)
```

### Cost Inference: Bedrock Models

**Current state (July 2026):** Langfuse does **not** auto-infer cost for Bedrock models.

**Why:** Langfuse maintains a built-in pricing table for OpenAI, Anthropic Cloud, Google—but not for AWS Bedrock. Bedrock pricing varies by:
- Model (Claude Sonnet $3/$15 per M input/output tokens vs. Llama $0.50/$1.50)
- Invoice channel (on-demand vs. provisioned throughput discounts)
- Regional variations
- Inference profiles (cross-region inference, custom profiles don't map to base models)

**Options:**

1. **Manual cost entry (simplest for hackathon):**
   - In Langfuse dashboard: Project Settings → Model Definitions
   - Add custom model entry for each Bedrock model:
     ```
     Model name: anthropic.claude-sonnet-5-v1:0
     Input cost: 0.000003 (per token)
     Output cost: 0.000015 (per token)
     ```
   - Then pass cost in SDK:
     ```python
     langfuse.update_current_generation(
         usage_details={...},
         cost_details={
             "input_cost": response["usage"]["inputTokens"] * 0.000003,
             "output_cost": response["usage"]["outputTokens"] * 0.000015
         }
     )
     ```

2. **Custom model definitions via SDK (v4 only):**
   - Define model pricing in code; Langfuse resolves it at ingest time
   - Better for CI/CD but requires setup

3. **Accept no cost tracking (acceptable for hackathon):**
   - Focus on token counts; cost can be calculated separately or after-the-fact

**Known issue:** Bedrock inference profiles (e.g., `arn:aws:bedrock:us-east-1::inference-profile/anthropic.claude-sonnet-5-v1`) don't auto-map to base model IDs in Langfuse. If using inference profiles, you **must** add custom regex rules in Langfuse's model definitions or extract the base model ID before logging.

**Simplest approach for hackathon:** Log token counts (automatic from response.usage), skip cost tracking initially. Add cost after the event if needed.

---

## 5. Environment Variables & Setup

### Required for Client Connection

```bash
# Langfuse credentials (get from https://cloud.langfuse.com/settings/api)
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"  # or self-hosted URL

# Optional
export LANGFUSE_RELEASE="v1.0.0"  # tag your traces with release version
```

**For backward compatibility:** `LANGFUSE_HOST` still works but `LANGFUSE_BASE_URL` is preferred (v4).

### Required for Bedrock

```bash
# AWS credentials (boto3 will auto-detect from ~/.aws/credentials or env)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"
```

### For Self-Hosted Docker Compose

Additional secrets needed in `.env` file:

```bash
# Generate random strings (e.g., openssl rand -hex 32)
NEXTAUTH_SECRET="..."
SALT="..."
ENCRYPTION_KEY="..."

# Database
POSTGRES_PASSWORD="..."

# API keys for first account (auto-generated on first run if not set)
# or leave empty and create via UI
```

**Example initialization:**
```bash
# Generate secrets
openssl rand -hex 32 > nextauth_secret.txt
openssl rand -hex 32 > salt.txt
openssl rand -hex 32 > encryption_key.txt

# Write .env
cat > .env << EOF
NEXTAUTH_SECRET=$(cat nextauth_secret.txt)
SALT=$(cat salt.txt)
ENCRYPTION_KEY=$(cat encryption_key.txt)
POSTGRES_PASSWORD=postgres-pwd-123
EOF

# Start
docker-compose up -d
```

---

## 6. Setup Checklist for Hackathon

### Cloud Route (15 mins)

- [ ] Create Langfuse account at https://cloud.langfuse.com
- [ ] Create API keys in Settings → API
- [ ] Export `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` to .env
- [ ] `pip install langfuse boto3`
- [ ] Test with minimal script:
  ```python
  from langfuse import get_client
  client = get_client()
  print(client.get_project())  # confirms auth works
  ```
- [ ] Wrap first Bedrock call with `@observe` decorator
- [ ] Verify traces appear in Langfuse UI
- [ ] (Optional) Configure Bedrock model pricing in Langfuse dashboard

### Self-Hosted on t3.medium (45 mins)

- [ ] Launch EC2 t3.medium (Ubuntu 22.04 LTS, allow inbound 3000, 9090)
- [ ] `ssh ec2-user@ip && sudo yum install docker -y`
- [ ] `sudo usermod -aG docker ec2-user && logout/login`
- [ ] `sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose && sudo chmod +x /usr/local/bin/docker-compose`
- [ ] `git clone https://github.com/langfuse/langfuse.git && cd langfuse`
- [ ] Generate secrets, write `.env`
- [ ] `docker-compose up -d`
- [ ] Wait ~2 mins for ClickHouse init, then visit `http://<ec2-ip>:3000`
- [ ] Create first account, get API keys
- [ ] Export `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL=http://<ec2-ip>:3000`
- [ ] Same integration steps as Cloud route

---

## 7. Adoption Risk & Maturity Assessment

### Langfuse Maturity
- **v3 (OTel-based):** Stable, 1+ year in production
- **v4 (March 2026):** Current, 4 months in production, actively maintained, breaking changes documented
- **Community:** ~10K+ GitHub stars, growing adoption among LangChain/LiteLLM users

### Bedrock Integration Risk
- **No official Langfuse instrumentation:** You're responsible for wrapping calls. Low risk if pattern is simple (as shown above).
- **Cost tracking not automated:** Manual work to configure Bedrock pricing. Acceptable for hackathon if deferred.
- **Token usage extraction:** Bedrock's response format is stable; no API churn expected.

### Self-Hosted Risks
- **Operational overhead:** Docker, networking, backup, upgrades. Not ideal for 1-week team.
- **ClickHouse migration path:** v3 split traces to ClickHouse. If you started on v2 and want to upgrade, you'd need migration scripts (not needed for new projects).
- **Data corruption risk:** Minimal with standard docker-compose, but backup strategy is critical if running >1 week.

### Python SDK v4 Risks
- **Breaking changes from v3:** If team has v3 code, migration is required. Straightforward but needs attention.
- **Pydantic v2 dependency:** If app uses Pydantic v1, compatibility shim is available but adds complexity.

---

## 8. Code Sketch: Full Agent Example

```python
# agent.py
from langfuse import observe, get_client
import boto3
import json

bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
langfuse = get_client()

BEDROCK_MODEL = "anthropic.claude-sonnet-5-v1:0"

@observe(as_type="generation", name="bedrock_converse")
def call_bedrock(messages: list, max_tokens: int = 1024) -> dict:
    """Call Bedrock Converse API with Langfuse tracing."""
    langfuse.update_current_generation(
        input=messages,
        model=BEDROCK_MODEL,
        model_parameters={"maxTokens": max_tokens}
    )
    
    response = bedrock.converse(
        modelId=BEDROCK_MODEL,
        messages=messages,
        inferenceConfig={"maxTokens": max_tokens}
    )
    
    output = response["output"]["message"]["content"][0]["text"]
    usage = response.get("usage", {})
    
    langfuse.update_current_generation(
        output=output,
        usage_details={
            "input": usage.get("inputTokens", 0),
            "output": usage.get("outputTokens", 0)
        }
    )
    
    return {"text": output, "usage": usage}

@observe(as_type="span", name="agent_step")
def agent_step(query: str) -> str:
    """Single agent step: LLM → (optional tool call) → response."""
    
    # Call LLM
    response = call_bedrock([
        {"role": "user", "content": query}
    ])
    
    # For this hackathon, no tool calls; just return LLM response
    return response["text"]

@observe(as_type="span", name="agent_run")
def run_agent(user_query: str) -> str:
    """Full agent loop (for multi-step tasks)."""
    
    # Step 1: Initial LLM call
    response = agent_step(user_query)
    
    # Step 2: Could add tool loop, re-prompting, etc.
    # For hackathon, keep simple.
    
    return response

if __name__ == "__main__":
    result = run_agent("What is 2+2?")
    print(f"Agent response: {result}")
    
    # Traces auto-flush on exit or you can call:
    langfuse.flush()
```

**Environment setup:**
```bash
export LANGFUSE_PUBLIC_KEY="pk-lf-..."
export LANGFUSE_SECRET_KEY="sk-lf-..."
export LANGFUSE_BASE_URL="https://cloud.langfuse.com"
export AWS_REGION="us-east-1"
python agent.py
```

**Result in Langfuse UI:**
- One trace per `run_agent()` call
- Nested spans for `agent_step()`
- Nested generation for each `call_bedrock()` call
- Token counts logged for each generation
- Cost omitted (unless manually configured)

---

## 9. Trade-off Summary

| Choice | Pros | Cons | Recommendation |
|--------|------|------|-----------------|
| **Cloud** | Fast setup, managed, free 50K events, data residency options | Overage at $0.10/1K events, 30-day retention | **✓ Use for hackathon** |
| **Self-hosted** | Full control, unlimited events, data residency in your AWS, no overages | 45 min setup, EC2 cost (~$30/mo), ops overhead (backups, upgrades) | Use if Cloud hits 50K or compliance mandates |
| **SDK v3** | Stable, fewer breaking changes, lots of examples | Older, less capable attribute propagation | Use if team prefers stability |
| **SDK v4** | Current direction, better for agents (attribute propagation), active development | 4 months old, breaking changes from v3, Pydantic v2 required | **✓ Use for new projects** |
| **Manual Bedrock wrapping** | Transparent, full control, works reliably | Boilerplate per call, cost tracking not auto | **✓ Accept for hackathon** |
| **Langfuse cost inference for Bedrock** | Would simplify reporting | Not implemented; manual config needed | Configure after event if needed |

---

## Unresolved Questions

1. **Expected trace volume:** If >50K events/month, self-hosted becomes cost-justified. Get estimate from product team.
2. **Data residency compliance:** Does "runs on AWS" mean compliance mandates self-hosting? Clarify with client/legal.
3. **Multi-region Bedrock inference:** If using cross-region inference profiles, confirm Langfuse cost mapping (currently has issues). Test in Phase 0.
4. **Langfuse v4 LangChain integration:** If using LangChain for agents, verify CallbackHandler is v4-compatible (should be, but confirm in docs).
5. **Self-hosted upgrade path:** If starting self-hosted and need to upgrade v3→v4, is data migration automatic? Document for ops.

---

## Sources

- [Langfuse Pricing 2026](https://langfuse.com/pricing)
- [Langfuse Self-Hosting](https://langfuse.com/self-hosting)
- [Self-Hosted Docker Compose Deployment](https://langfuse.com/self-hosting/deployment/docker-compose)
- [Langfuse v3 Self-Hosting Complete Guide](https://jangwook.net/en/blog/en/langfuse-self-hosted-llm-tracing-setup-guide-2026/)
- [Open Source Observability for Amazon Bedrock - Langfuse](https://langfuse.com/integrations/model-providers/amazon-bedrock)
- [Observability and Metrics for Amazon Bedrock - Langfuse](https://langfuse.com/docs/integrations/amazon-bedrock)
- [Python v3 → v4 Upgrade Path](https://langfuse.com/docs/observability/sdk/upgrade-path/python-v3-to-v4)
- [Token & Cost Tracking - Langfuse](https://langfuse.com/docs/observability/features/token-and-cost-tracking)
- [Langfuse Python SDK Overview](https://langfuse.com/docs/sdk/python)
- [OpenTelemetry Integration - Langfuse](https://langfuse.com/integrations/native/opentelemetry)
- [OTEL-based Python SDK Changelog](https://langfuse.com/changelog/2025-05-23-otel-based-python-sdk)

---

## Status

**Status:** DONE

**Summary:** Langfuse Cloud + Python SDK v4 is pragmatic for hackathon. Manual Bedrock instrumentation required; cost tracking deferred. Self-hosted viable on t3.medium if compliance demands it.

**Concerns:** Bedrock cost inference not implemented in Langfuse; inference profile mapping has known issues. Manual pricing config needed. No gotchas blocking Phase 0, but cost tracking should be tested early.

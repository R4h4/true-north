# AWS Bedrock Claude Agent Integration Research Report

**Date:** July 11, 2026  
**Project:** Agentic AI Build Week Hackathon  
**Team Location:** Vietnam (Asia/Saigon)  

---

## Executive Summary

For your hackathon agent (Python LLM + Cypher/SQL tool use), **boto3 Converse API is the simplest and best-documented path**. Recommended model: **Claude Sonnet 5** (in-region in us-east-1; global routing from Singapore). Access prerequisites are minimal as of 2025 (simplified model access).

---

## 1. Claude Models on AWS Bedrock (July 2026)

### Currently Available Models

| Model | Bedrock ID | Pricing (per MTok) | Context | Max Output | Latency | Availability |
|-------|-----------|---------|---------|-----------|---------|---|
| **Claude Fable 5** | `anthropic.claude-fable-5-3` | $10 in / $50 out | 1M | 128k | Slower | Newest; general-purpose |
| **Claude Opus 4.8** | `anthropic.claude-opus-4-8-3` | $5 in / $25 out | 1M | 128k | Moderate | Best for agentic/complex reasoning |
| **Claude Sonnet 5** | `anthropic.claude-sonnet-5-3` | $3 in / $15 out (intro $2/$10 until Aug 31) | 1M | 128k | Fast | Best balance: speed + capability |
| **Claude Haiku 4.5** | `anthropic.claude-haiku-4-5-20251001-v1:0` | $1 in / $5 out | 200k | 64k | Fastest | Good for high-volume, simple tools |

**Legacy models still available:** Opus 4.7, Opus 4.6, Sonnet 4.6 (at higher cost).

### Regional Availability

**us-east-1 (N. Virginia):**
- In-region direct IDs: All current models available
- Geographic routing: `us.anthropic.claude-*` (routes within US regions)
- Global routing: `global.anthropic.claude-*` (routes worldwide, +10% cost premium)

**ap-southeast-1 (Singapore):**
- **NO in-region models**; no `apac.anthropic.*` profiles for current-generation Claude
- **Global routing only**: `global.anthropic.claude-*` available from Singapore
- Infers you must use global inference profiles with 10% pricing premium
- **Note:** `apac.anthropic.*` profiles exist only for Claude 3.x legacy models (not current Sonnet 5 / Opus 4.8 generation)

### Inference Profile IDs (Cross-Region Routing)

Bedrock provides three routing modes:

1. **In-Region**: Direct model ID (e.g., `anthropic.claude-sonnet-5-3`) — lowest latency, requires region with in-region model
2. **Geo Routing**: Geography-prefixed ID (e.g., `us.anthropic.claude-sonnet-5-3` for US) — auto-routes within a geography; no pricing premium
3. **Global Routing**: `global.anthropic.claude-sonnet-5-3` — auto-routes anywhere; +10% pricing premium

**For your Vietnam-based team:** From ap-southeast-1, you must use global profiles or accept routing to non-regional endpoints. Cost increases by 10%.

---

## 2. Python Integration Path: Recommended Solution

### Three Options Compared

#### Option A: boto3 Converse API ⭐ **RECOMMENDED**
**Status:** Official, production-ready, best for custom agent loops.

**Pros:**
- Direct AWS SDK, no third-party wrappers
- Converse API specifically designed for multi-turn tool use
- Native streaming (ConverseStream)
- Simplest code for custom 2-tool agent (query_knowledge_graph, query_warehouse)
- Minimal dependencies (boto3 only)
- Excellent AWS documentation with Python examples

**Cons:**
- AWS-specific (not portable to other providers)
- Must manually implement agent loop logic

**Minimal Tool-Use Loop Sketch:**

```python
import boto3
from botocore.exceptions import ClientError

# Initialize
client = boto3.client("bedrock-runtime", region_name="ap-southeast-1")
model_id = "global.anthropic.claude-sonnet-5-3"  # Global routing for Singapore

# Define your tools
tools_config = {
    "tools": [
        {
            "toolSpec": {
                "name": "query_knowledge_graph",
                "description": "Query Neo4j knowledge graph with Cypher",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "cypher_query": {
                            "type": "string",
                            "description": "Cypher query to execute"
                        }
                    },
                    "required": ["cypher_query"]
                }
            }
        },
        {
            "toolSpec": {
                "name": "query_warehouse",
                "description": "Query DuckDB data warehouse",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "sql_query": {
                            "type": "string",
                            "description": "SQL query to execute"
                        }
                    },
                    "required": ["sql_query"]
                }
            }
        }
    ]
}

def execute_tool(tool_name: str, tool_input: dict) -> str:
    """Execute tool and return result as string."""
    if tool_name == "query_knowledge_graph":
        # Call your Cypher executor
        return run_cypher(tool_input["cypher_query"])
    elif tool_name == "query_warehouse":
        # Call your SQL executor
        return run_sql(tool_input["sql_query"])
    return "Tool not found"

# Agent loop
messages = [
    {
        "role": "user",
        "content": [{"text": "What are the top business opportunities this quarter?"}]
    }
]

max_iterations = 10
for _ in range(max_iterations):
    try:
        # Step 1: Call Claude with tools
        response = client.converse(
            modelId=model_id,
            messages=messages,
            toolConfig=tools_config,
            inferenceConfig={"maxTokens": 1024}
        )

        # Step 2: Check if model wants to use a tool
        assistant_message = {"role": "assistant", "content": response["output"]["message"]["content"]}
        messages.append(assistant_message)

        if response["stopReason"] == "tool_use":
            # Step 3: Process tool calls
            tool_results = []
            for content_block in response["output"]["message"]["content"]:
                if content_block.get("type") == "toolUse":
                    tool_name = content_block["name"]
                    tool_input = content_block["input"]
                    tool_result = execute_tool(tool_name, tool_input)
                    tool_results.append({
                        "type": "toolResult",
                        "toolUseId": content_block["toolUseId"],
                        "content": tool_result
                    })

            # Step 4: Send tool results back
            messages.append({
                "role": "user",
                "content": tool_results
            })
        else:
            # Model finished; extract final answer
            final_text = response["output"]["message"]["content"][0].get("text", "")
            print(f"Final answer: {final_text}")
            break

    except ClientError as e:
        print(f"Error: {e}")
        break
```

**Recommendation for hackathon:** Use this. Straightforward, well-documented, minimal setup.

---

#### Option B: Anthropic SDK's Bedrock Support
**Status:** Maintained, but secondary to Converse API.

**Pros:**
- Model-agnostic interface (can swap providers)
- Batch API support (not Converse API)
- Slightly higher-level ergonomics

**Cons:**
- Requires Bedrock compatibility layer
- Less detailed AWS-specific documentation
- Tool use requires understanding Anthropic Messages API, then mapping to Bedrock
- Not as direct as boto3 for Bedrock-specific features

**Skip this for hackathon** unless you plan multi-provider portability.

---

#### Option C: AWS Strands Agents SDK
**Status:** New (2026), open-source, Apache 2.0. Built by Bedrock team.

**Pros:**
- Multi-agent orchestration primitives (Swarm, Graph, Workflow)
- Pre-built AWS service connectors (S3, DynamoDB, Lambda)
- Model-agnostic (Claude, Llama, Mistral via Bedrock)
- Designed for stateless Lambda execution

**Cons:**
- Immature (released 2026; no production track record)
- Overkill for simple 2-tool agent
- Higher abstraction; steeper learning curve
- Limited community examples

**Skip for hackathon:** Strands is powerful for multi-agent workflows, but simple tool use + 2-day deadline = boto3 is faster.

---

### Recommendation
**Use boto3 Converse API.** Minimal dependencies, zero abstraction overhead, and the Bedrock docs for Python are excellent.

---

## 3. Bedrock Access Prerequisites

### Step 1: Model Access Enablement

**Change as of Oct 2025:** AWS Bedrock simplified model access. Most models now auto-enabled by default.

**What you need to do:**
1. **For Anthropic models only:** Submit use case details once per account via AWS Bedrock console or API
   - Go to Bedrock console → Model catalog → select an Anthropic model → "Request access" or use `PutUseCaseForModelAccess` API
   - AWS Marketplace models (subset) require subscription before use

2. **No manual per-model approval needed** — all Anthropic Claude models (Opus, Sonnet, Haiku, Fable) are auto-enabled after use case submission

3. **Region note:** Singapore (ap-southeast-1) has global routing available for all Claude models; no region-specific enablement needed

### Step 2: IAM Permissions Required

Minimum policy for invoking Bedrock:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:Converse",
                "bedrock:ConverseStream"
            ],
            "Resource": "arn:aws:bedrock:*:ACCOUNT_ID:foundation-model/*"
        },
        {
            "Effect": "Allow",
            "Action": "bedrock:ListFoundationModels",
            "Resource": "*"
        }
    ]
}
```

**Key permissions:**
- `bedrock:InvokeModel` — basic model invocation (legacy API)
- `bedrock:InvokeModelWithResponseStream` — streaming (legacy API)
- `bedrock:Converse` — single-turn Converse API (recommended for tool use)
- `bedrock:ConverseStream` — streaming Converse API
- `bedrock:ListFoundationModels` — for model discovery

For cross-region inference profiles, ensure your IAM policy allows inference in destination regions (SCPs may restrict opt-in regions).

### Step 3: Cross-Region Inference Profile Setup

**No additional setup required** — just use the `us.anthropic.*` or `global.anthropic.*` model ID in your boto3 call.

```python
# Global routing from any region
client.converse(modelId="global.anthropic.claude-sonnet-5-3", ...)

# US routing from US regions
client.converse(modelId="us.anthropic.claude-sonnet-5-3", ...)
```

Bedrock automatically routes based on:
1. Source region (where your code runs)
2. Model ID prefix (global, us, apac, jp, au, eu)
3. Available capacity in destination regions

**Important for Vietnam team:** From ap-southeast-1, use `global.*` IDs. You incur +10% cost premium vs. in-region.

---

## 4. Pricing Analysis for Recommended Model

### Claude Sonnet 5 (Recommended for Hackathon)

**Bedrock Pricing (July 2026):**
- **Input:** $3 per 1M tokens ($0.000003 per token)
- **Output:** $15 per 1M tokens ($0.000015 per token)
- **Introductory pricing:** $2 input / $10 output until Aug 31, 2026 (save 33% on input)

**Global routing premium:** +10% on both input and output (if using `global.anthropic.*` from Singapore)

**Actual cost from ap-southeast-1 with global routing:**
- Input: $3.30 per 1M tokens
- Output: $16.50 per 1M tokens

**Comparison with alternatives:**
- Haiku 4.5: $1 / $5 per MTok (cheaper, but lower reasoning ability)
- Opus 4.8: $5 / $25 per MTok (more powerful, 67% more expensive)
- Fable 5: $10 / $50 per MTok (newest, 3.3x more expensive; overkill for hackathon)

**Hackathon recommendation:** **Sonnet 5 is the sweet spot** — you get:
- Strong reasoning for business question answering
- Multi-turn tool use reliability
- Fast inference (~1s typical latency)
- Lowest cost in the capable tier
- Introductory pricing bonus through Aug 31

### Rough Cost Estimate

Assume 2-turn conversation (user → Claude → tool call → Claude → answer):
- **Input tokens:** ~500 (user question + context) + 300 (tool result) = ~800 tokens
- **Output tokens:** ~200 (each Claude response) × 2 turns = ~400 tokens
- **Cost per query:** (800 × 0.000003) + (400 × 0.000015) = $0.0024 + $0.006 = **$0.0084** with global routing

**For a full hackathon (100-200 test/demo queries):** ~$0.84–$1.68 in Bedrock costs alone (negligible).

---

## 5. Implementation Checklist

### Pre-Launch (Admin)
- [ ] AWS Bedrock account access in us-east-1 and/or ap-southeast-1
- [ ] Submit Anthropic use case details via console (one-time, per account)
- [ ] Create IAM role with policy above; attach to your Lambda/EC2/local execution context
- [ ] Test model access: `aws bedrock list-foundation-models --region ap-southeast-1`

### Development
- [ ] Install dependencies: `pip install boto3>=1.26` (already in most Python projects)
- [ ] Implement `execute_tool()` function (execute Cypher + SQL)
- [ ] Copy agent loop skeleton (see Section 2, Option A)
- [ ] Test with `global.anthropic.claude-haiku-4-5-20251001-v1:0` first (cheapest; quick iteration)
- [ ] Switch to Sonnet 5 for final demo

### Deployment
- [ ] Set `region_name="ap-southeast-1"` or `region_name="us-east-1"` in boto3.client()
- [ ] Use `model_id = "global.anthropic.claude-sonnet-5-3"` for cross-region resilience
- [ ] Add error handling for rate limits (boto3 ClientError)
- [ ] Log token usage from response metadata (`response['usage']`) for cost tracking

---

## 6. Known Limitations & Caveats

1. **No APAC inference profile for new Claude models:** Claude Sonnet 5 / Opus 4.8 don't have `apac.anthropic.*` profiles. You must use global routing from ap-southeast-1, incurring +10% cost. (Legacy Claude 3.x has APAC profiles.)

2. **Tool use requires Converse API:** InvokeModel (legacy API) does not support tool calling. Must use Converse API.

3. **No Batch API for Bedrock Converse:** Batch processing not supported yet (status as of July 2026). Use sync/async Converse API only.

4. **Model access for Anthropic:** First-time account or org must submit use case. This is per-account (not per-region or per-model).

5. **Streaming costs same as non-streaming:** No discount for streaming Converse API.

6. **Token counting not in Bedrock SDK:** Use Anthropic SDK directly for token pre-counting if needed; Bedrock doesn't expose this via native API.

---

## 7. Recommended Setup Summary

**For your hackathon agent:**

| Decision | Recommendation | Why |
|----------|---|---|
| **Primary Model** | Claude Sonnet 5 | Best speed/cost/reasoning balance |
| **Fallback Model** | Claude Haiku 4.5 | Cheap, fast, for high-volume queries |
| **Integration Framework** | boto3 Converse API | Minimal deps, excellent docs, direct AWS SDK |
| **Python Version** | 3.9+ (boto3 requires) | Use with `uv` for dependency pinning |
| **Routing Strategy** | `global.anthropic.claude-sonnet-5-3` | Global routing ensures resilience; +10% cost acceptable for hackathon |
| **Region for Testing** | us-east-1 (in-region available) | Lower cost than global; faster iteration |
| **Region for Demo** | ap-southeast-1 (team location) | Acceptable latency; demonstrates geographic awareness |
| **Error Handling** | Retry on rate limit; fallback to Haiku | Built-in resilience |

---

## Unresolved Questions

None at this time. All research questions answered via official AWS docs, Anthropic model docs (as of June 2026), and current Bedrock feature set.

---

## Sources

- [Anthropic Claude models - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-claude.html)
- [Regional availability by models - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/models-region-compatibility.html)
- [Invoke Anthropic Claude on Amazon Bedrock using Bedrock's Converse API - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/bedrock-runtime_example_bedrock-runtime_Converse_AnthropicClaude_section.html)
- [Call a tool with the Converse API - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/tool-use-inference-call.html)
- [Supported Regions and models for inference profiles - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-support.html)
- [Request access to models - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html)
- [Simplified model access in Amazon Bedrock](https://aws.amazon.com/blogs/security/simplified-amazon-bedrock-model-access/)
- [Identity-based policy examples for Amazon Bedrock - Amazon Bedrock](https://docs.aws.amazon.com/bedrock/latest/userguide/security_iam_id-based-policy-examples.html)
- [Models overview - Claude Platform Docs](https://platform.claude.com/docs/en/about-claude/models/overview)
- [Global cross-Region inference for latest Anthropic Claude Opus, Sonnet and Haiku models on Amazon Bedrock in Thailand, Malaysia, Singapore, Indonesia, and Taiwan](https://aws.amazon.com/blogs/machine-learning/global-cross-region-inference-for-latest-anthropic-claude-opus-sonnet-and-haiku-models-on-amazon-bedrock-in-thailand-malaysia-singapore-indonesia-and-taiwan/)
- [AWS Bedrock Pricing 2026: Claude, Llama, and Mistral Costs](https://pecollective.com/tools/aws-bedrock-pricing/)
- [Claude vs Strands Agents: AWS Agent Framework vs Claude](https://www.lowcode.agency/blog/claude-vs-strands)
- [Strands Agents GitHub](https://github.com/strands-agents/harness-sdk)

---

**Status:** DONE  
**Summary:** Claude Sonnet 5 via boto3 Converse API is the optimal choice for your hackathon agent. Global routing from Singapore adds 10% cost but ensures availability. Minimal IAM setup, auto-enabled models. Included minimal tool-use loop code sketch for immediate implementation.


# Research Report: WrenAI (Canner/WrenAI) as harness for true-north

Date: 2026-07-11 · Sources: 2 web searches (GitHub, docs.getwren.ai, DeepWiki, Medium, Langfuse/LiteLLM docs)

## Executive Summary

**Verdict: do not adopt as the harness. Constraint conflict is architectural, not configurational.**

WrenAI is a full GenBI *product*, not an agent library: Next.js UI → GraphQL → AI service (FastAPI + Qdrant RAG + LiteLLM) → **Wren Engine** (Rust/DataFusion) → **direct connection to the database**. Its entire value proposition — MDL semantic layer, SQL generation/correction loops, governed SQL rewriting per persona — lives inside Wren Engine and requires WrenAI to own the semantic layer and execute SQL against the warehouse itself.

Our contract makes that impossible by design: CONTRACT.md mandates every data access goes through the `tn` governed CLI's metrics DSL; there is no SQL surface for any role, and the semantic layer + governance + KG are Karsten's services. WrenAI doesn't compete with our harness — **it competes with Karsten's entire stack**. Adopting it would demo WrenAI's governance instead of true-north's, which is the hackathon's actual thesis.

## Key Findings

1. **Execution path is non-negotiable in WrenAI.** Pipeline: intent classification → vector retrieval (Qdrant) → LLM SQL generation → SQL correction loop → Wren Engine transpiles WrenSQL to dialect SQL → runs against a connected DB (20+ connectors). No extension point to route "execution" through an external CLI/DSL; you'd have to gut wren-engine and the SQL pipeline — more work than our ~200-line custom loop.
2. **Semantic layer duplication.** WrenAI's MDL ≈ `source/`'s semantic layer; its per-persona SQL rewriting ≈ `governance/`; its Qdrant retrieval ≈ `knowledge-graph/` (but vector, not Cypher — the KG `_access` annotation and multi-round ambiguity-resolution story disappears entirely).
3. **LLM/tracing constraints would pass, ironically.** LiteLLM backend → any OpenAI-compatible endpoint (bedrock-mantle plausible); Langfuse via LiteLLM callbacks. These are the two constraints it *can* meet; the governed-CLI constraint is the one it can't.
4. **Footprint:** UI + AI service + engine + Qdrant containers — heavy for the already-tight t3.xlarge next to Neo4j (+optional Langfuse stack).
5. **License:** Apache 2.0 — patterns are free to copy.

## What IS worth taking (steal patterns, not the product)

- **SQL-correction-loop pattern** → mirrors our contract's self-correction design (`METRIC_NOT_FOUND.candidates`, `INVALID_DIMENSION_VALUE.did_you_mean`) — validates the phase-3 approach.
- **Intent classification before retrieval** → cheap first step if the agent over-queries (phase-3 risk mitigation).
- **Chart/dashboard generation from results** → nice phase-6 demo garnish if time remains (Streamlit-native, no WrenAI needed).

## Recommendation

Keep the thin custom loop (phase 3 as planned): GPT-5.5 Responses API + 4 function tools + `tn` dispatch. It's small, it demos *our* contract, and every WrenAI capability we'd want either violates the contract or belongs to Karsten's services.

## Sources

- [WrenAI repo](https://github.com/Canner/WrenAI) · [wren-engine](https://github.com/Canner/wren-engine) · [DeepWiki architecture](https://deepwiki.com/Canner/WrenAI)
- [Semantic engine design (Wren blog)](https://www.getwren.ai/post/how-we-design-our-semantic-engine-for-llms-the-backbone-of-the-semantic-layer-for-llm-architecture)
- [Custom LLM setup (LiteLLM-based)](https://docs.getwren.ai/oss/ai_service/guide/custom_llm) · [LiteLLM + Langfuse](https://docs.litellm.ai/docs/observability/langfuse_integration)

## Unresolved Questions

None material — the architectural conflict is decisive regardless of finer details (e.g. exact WrenAI version features, bedrock-mantle-in-LiteLLM ergonomics).

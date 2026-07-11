# 0005 — Real Neo4j via docker-compose, not an embedded engine

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

`tn kg query` accepts read-only Cypher written by an LLM agent. The canonical queries
frozen into `tn kg schema`, the replay fixtures, and Phong's system prompt use `=~`
regex, `OPTIONAL MATCH`, and `collect(DISTINCT …)`. An embedded engine (Kuzu) would
remove the docker dependency but speaks a Cypher dialect with enough divergence to risk
breaking already-frozen queries.

## Decision

Neo4j (community) in docker-compose. The CLI talks bolt with a read-only session plus a
pre-check on write clauses so rejections surface as clean `QUERY_REJECTED` envelopes.
Graph contents are a build artifact: full wipe-and-rebuild on compile (ADR 0007's
derivations included), stamped `graph_compiled_at`.

## Consequences

Full Cypher compatibility and a free browser UI for the pitch. Cost: `docker compose up`
becomes part of the demo bring-up and of running the real conformance/e2e suites —
acceptable because `make demo` is required anyway (ADR 0004).

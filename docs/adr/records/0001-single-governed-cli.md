# 0001 — Single governed CLI as the only harness-facing interface

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

Two people build in parallel: the harness (agent, chat) and the data/governance stack
(warehouse, semantic layer, knowledge graph). The harness needs the knowledge graph for
context and the warehouse for numbers; permissions must apply to *both* — including
permission annotations inside graph answers, which raw bolt access can't provide. The
integration seam had to be one thing that can be specified, stubbed, and conformance-tested
before either side is real.

## Decision

Exactly one interface: the `tn` CLI, specified in `CONTRACT.md`. Every call carries an
auth token; the CLI fronts both surfaces (Cypher over the graph, metrics DSL over the
warehouse) and always answers with one JSON envelope. Cypher moved *behind* the CLI
precisely so the token can inject `_access` metadata into graph answers.

## Consequences

The two halves develop against a contract instead of each other. A stub can honor the
whole interface (ADR 0004). Cost: everything is a subprocess call — no streaming, no
connection reuse; acceptable at demo scale. The Neo4j browser stays human-only and
non-contractual.

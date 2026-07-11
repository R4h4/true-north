---
phase: 4
title: "Karsten Track: Semantic Layer & Governed Services"
status: pending
priority: P1
dependencies: [1]
---

# Phase 4: Karsten Track: Semantic Layer & Governed Services

## Overview

Karsten's parallel track, documented here **at contract level only** — internals of
`source/`, `governance/`, `knowledge-graph/` are his to design. This plan records what the
other track depends on: the real governed CLI passing the shared conformance suite, and
the checkpoints where the tracks touch.

## Requirements

- Functional: a real `governed-cli` implementing the Phase 1 contract — token resolution
  from `contracts/personas.json`, **metrics-DSL requests compiled to SQL by the semantic
  layer** (raw SQL is never exposed) with row/column/table governance applied, a
  `metrics` discovery listing, and Cypher against a Neo4j populated by semantic-layer
  ingest (metrics, dimensions, glossary, **permission metadata**).
- Non-functional: conformance suite (`contracts/conformance/`) green, unmodified except by
  joint PR; Neo4j runs from the `infra/` docker-compose (Phase 5) or a compatible local
  container (`neo4j:5-community`, bolt on 7687).

## Architecture

Owned by Karsten. The contract constrains only the edges:

- CLI entrypoint installable/runnable via uv so the harness can set
  `GOVERNED_CLI_CMD="uv run --project governance governed-cli"` (exact command is Karsten's
  choice — announced in the contract changelog when it stabilizes).
- KG must contain, per governed metric: definition, caveats (TRAPS.md material), backing
  tables, and per-persona access info — enough Cypher-reachable structure to answer
  "metric exists but you don't have access". The **queryable shape (labels, relationship
  types, property names) is frozen in the Phase 1 contract**; ingest internals are free,
  but the agent's Cypher must work unchanged. Ingest must be idempotent (`MERGE`, not
  `CREATE`) — the demo box stops/starts and re-runs it.
- Governance semantics must match `contracts/personas.json` exactly (same fixture the mock
  uses — single source of truth for permissions).

## Related Code Files

- Create (Karsten's directories, layout his call): `source/` semantic layer + DSL,
  `governance/` engine + CLI, `knowledge-graph/` ingest job.
- Modify: `docs/governed-cli-contract.md` changelog (only via joint PR).

## Implementation Steps

(Coarse — Karsten refines in his own plan/issues.)

1. Semantic layer in `source/`: governed metric/dimension definitions over the star schema.
2. Governance engine: token → persona → row filter / column mask / table ACL, wrapping the
   existing read-only query engine.
3. `governed-cli` binding both surfaces; run conformance suite against it early and often.
4. KG ingest: semantic layer + permission metadata → Neo4j; wire `graph` subcommand.
5. Test against generated data from plan `260711-1547-phongvu-demo-data` (tiny/small scale
   suffices until that plan lands full scale).

## Success Criteria

- [ ] `GOVERNED_CLI_CMD=<real cli> uv run pytest contracts/conformance/` green with zero
  test edits (or edits agreed via joint PR).
- [ ] The three personas produce the governance behaviors fixed in Phase 1's table.
- [ ] KG answers a "define revenue" Cypher query with metric + caveats + access info.
- [ ] Hard gate honored: the day conformance first goes green, a 1-hour joint
  harness↔real-CLI smoke runs (mid-build — Phase 6 must not be first contact); second
  checkpoint when the KG is populated.

## Risk Assessment

- **This phase slips past demo day** → Phase 2 mock IS the fallback demo path: harness +
  mock still demonstrates governance UX end-to-end; degrade scope, not the demo.
- **Contract turns out wrong once real governance is built** → changelog + conformance
  update via joint PR; mock updated in the same commit so both tracks stay green.
- **Permissions fixture diverges between mock shim and real engine** → both read
  `contracts/personas.json`; never fork it.

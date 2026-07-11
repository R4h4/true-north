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

- Functional: the real `tn` CLI implementing CONTRACT.md v0.3 (replacing the stub behind
  the same entrypoint and goldens) — **metrics-DSL requests compiled to SQL by the
  semantic layer** (raw SQL is never exposed) with permissions applied at compile time,
  `metrics`/`dimensions` discovery, and `kg query`/`kg schema` against a Neo4j populated
  by the compile step (metrics, dimensions, concepts, constraints, **`_access` permission
  annotation per calling user**).
- Non-functional: conformance suite (`contracts/conformance/`) green, unmodified except by
  joint PR; Neo4j runs from the `infra/` docker-compose (Phase 5) or a compatible local
  container (`neo4j:5-community`, bolt on 7687).

## Architecture

Owned by Karsten. The contract constrains only the edges:

- CLI entrypoint is `uv run tn` from the repo root (fixed by CONTRACT.md; the harness's
  `GOVERNED_CLI_CMD` already defaults to it — stub→real is invisible to the harness).
- KG must contain, per governed metric: definition, caveats (TRAPS.md material), backing
  tables, and per-persona access info — enough Cypher-reachable structure to answer
  "metric exists but you don't have access". The **queryable shape (labels, relationship
  types, property names) is frozen in CONTRACT.md §4** — labels, relationships, the four
  invariants, and `_access` annotation on Metric/Table/Dimension nodes; compile-step
  internals are free, but the agent's Cypher must work unchanged. The compile must be
  idempotent (`MERGE`, not `CREATE`) — the demo box stops/starts and re-runs it.
- Persona **observable behavior** per CONTRACT.md §1 is the guarantee (tokens, row-filter
  region South, banded birth years, tokenized ids, denial reasons);
  `governance/fixtures/users.yaml` is internal and may change shape freely.

## Related Code Files

- Create (Karsten's directories, layout his call): `source/` semantic layer + DSL,
  `governance/` engine + CLI, `knowledge-graph/` ingest job.
- Modify: `CONTRACT.md` changelog + `contracts/examples/` goldens (contract rule: same
  PR, reviewed by Phong).

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
- [ ] The four contract personas produce the observable behaviors of CONTRACT.md §1.
- [ ] KG answers a "define revenue" Cypher query with metric + caveats + access info.
- [ ] Hard gate honored: the day conformance first goes green, a 1-hour joint
  harness↔real-CLI smoke runs (mid-build — Phase 6 must not be first contact); second
  checkpoint when the KG is populated.

## Risk Assessment

- **This phase slips past demo day** → the stub IS the fallback demo path: harness +
  stub still demonstrates governance UX end-to-end; degrade scope, not the demo.
- **Contract turns out wrong once real governance is built** → CONTRACT.md changelog +
  goldens update in the same PR (contract rule); stub fixtures updated in the same commit
  so both tracks stay green.
- **Stub and real CLI diverge on persona behavior** → observable behavior is pinned in
  CONTRACT.md §1 and exercised by the goldens; the conformance suite catches forks.

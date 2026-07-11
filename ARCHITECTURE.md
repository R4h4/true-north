# ARCHITECTURE.md — true-north

> Stable mental map. Names, not links. Revisit on real structural change.
> For *why* a decision was made, see `docs/adr/`. For *what* the interface
> guarantees, `CONTRACT.md` (normative). This file is descriptive.

## System context

```
 business user ──chat──► harness (Bedrock agent + Langfuse)          [Phong]
                             │
                             │  governed CLI `tn`  — the ONLY interface
                             │  (auth token → user → permissions, JSON envelope)
              ┌──────────────┴────────────────┐
              │ Cypher (read-only)            │ metrics DSL (no raw SQL)
     ┌────────▼─────────┐            ┌────────▼─────────┐
     │  knowledge-graph │            │    governance    │             [Karsten]
     │  Neo4j: glossary │            │  token→persona,  │
     │  + compiled      │            │  row filters,    │
     │  metrics/dims/   │            │  masking, tokens │
     │  roles, _access  │            │  + `tn` entry    │
     └────────┬─────────┘            └────────┬─────────┘
              │ compiled from                 │ compiles + executes
     ┌────────▼─────────────────────────────▼──────────┐
     │                    source                        │             [Karsten]
     │  DuckDB warehouse (synthetic Phong Vũ star       │
     │  schema, planted traps) + semantic layer YAML    │
     └──────────────────────────────────────────────────┘
```

## Structure

```
CONTRACT.md               normative CLI interface; changes only via PR that updates goldens
contracts/
  examples/               golden request/response pairs (structure-normative)
  conformance/            pytest suite run against any `tn` via GOVERNED_CLI_CMD
source/
  generator/              schema.py (single source of truth for tables/columns/vocabularies),
                          deterministic data generator (--scale, --seed)
  semantic/               metrics/*.yml, dimensions/*.yml (see SCHEMA.md) — the governed layer
  query/                  read-only DuckDB engine
  data/TRAPS.md            the planted failure modes; features, not bugs
governance/
  fixtures/users.yaml     single policy source: tokens, roles, grants (see POLICY.md)
  governance/             the `tn` CLI (Typer) — entrypoint for BOTH surfaces
knowledge-graph/
  vocabulary/             concepts/*.yml, constraints/*.yml (see SCHEMA.md) — authored graph half
  knowledge_graph/        compiler: vocabulary + semantic + policy → Neo4j; docker-compose
harness/                  Phong's tree: agent, chat, charting; consumes `tn` and nothing else
tools/
  validators/             semantic / vocabulary / policy validators (pre-commit + `make validate`)
  tests/                  validator specs + TN_E2E-gated cross-call integration tests
docs/                     USING-TN.md (agent guide), adr/ (decision log), domain research
plans/                    Phong's phase plans (reviewed via PR)
```

## How the modules relate

- `source/generator/schema.py` is the **single shared truth** for physical tables, columns,
  and canonical vocabularies. The generator, the semantic layer, the validators, and the
  policy file all resolve against it; nothing redeclares columns.
- `source/semantic/` is the second truth: the governed metric/dimension definitions.
  The SQL compiler executes them; the KG compiler projects them into graph nodes;
  `governance/fixtures/users.yaml` grants against the physical objects they reference.
  Metric/dimension **denials are always derived** (policy × semantic layer), never authored.
- `governance/` owns the `tn` entrypoint and the persona resolution; both surfaces
  (warehouse, graph) go through it so every answer carries the caller's permissions.
- `harness/` depends only on `CONTRACT.md` + the CLI. Nothing below the CLI is interface.
- `tools/` depends on everything and is depended on by nothing (validators, e2e tests).

## State & storage

- **Warehouse**: parquet files generated deterministically (seed 42; tiny/small/full);
  gitignored — only headers-only CSVs are committed. DuckDB runs embedded, read-only.
- **Graph**: Neo4j in docker-compose; contents are a **build artifact** — full
  wipe-and-rebuild on compile, stamped `graph_compiled_at`. Never edited in place;
  the browser UI is for humans and is non-contractual.
- **No runtime state anywhere else**: tokens are static fixtures, tokenization is
  deterministic (HMAC) within a run, every `tn` call is stateless. Determinism is a
  tested property (identical call → identical envelope).

## Phases

1. **Contract** — CONTRACT.md v0.3 + goldens (done, PR #2).
2. **Stub** — replay `tn` + conformance suite so the harness develops against the real
   interface shape (done, PR #4). The stub dies when phase 4 passes conformance.
3. **Harness** — Phong: Bedrock agent, chat, Vega-Lite charting, Langfuse traces
   (in flight against the stub).
4. **Real services** — scaffolding PR (schemas, validators, e2e gate), then in parallel:
   semantic layer + SQLGlot compiler + real query surface ∥ vocabulary + Neo4j compiler
   + real graph surface (in flight).
5. **Demo** — `make demo` one-command bring-up; four scripted persona conversations
   (Phong's DoD) against real services.

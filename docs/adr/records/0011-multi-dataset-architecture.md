# 0011 — Multi-dataset (multi-tenant) architecture

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

The whole system was single-tenant: the warehouse data dir, the semantic YAML,
`schema.py`, the KG vocabulary, `users.yaml`, the Neo4j bolt URI, and the
Postgres store were all hard-coded retail paths, scattered across
`query.engine`, `semantic_layer`, `knowledge_graph.config`/`compile`, and
`governance.pg`/`service`/`cli`. The pitch now needs a second dataset (`shinhan`,
a bank) served by the same governed CLI, with hard isolation between tenants —
one tenant's query must never see another's data, graph, or policy — and with
**zero churn to retail**: every existing golden byte-identical, the existing
Postgres tables and `alembic_version` untouched, the CLI hot path still free of
SQLAlchemy/Alembic (ADR 0010).

Two isolation problems have different shapes. The warehouse is DSL-compiled, so
row/column scoping is already governed per query — but the KG surface accepts
**arbitrary read-only Cypher**, which cannot be reliably tenant-scoped inside a
shared graph (a `MATCH (n) RETURN n` would cross tenants). Postgres holds both
authored-runtime policy and an append-only audit log that must not intermingle
across tenants.

## Decision

**One registry seam.** `semantic_layer.datasets` maps a dataset key to a frozen
`Dataset` bundle: `data_dir`, `semantic_dir`, `schema_py`, `vocab_dir`,
`users_yaml`, `pg_schema`, and `bolt_uri()`. Everything that hard-coded a retail
path now resolves through `get_dataset(key)`. Resolution precedence is **explicit
key > `TN_DATASET` env > `retail`**; an unregistered key raises `UnknownDataset`
(naming the valid keys). Registry entries are pure path math — constructing or
resolving a Dataset never requires its files to exist, so the `shinhan` entry is
valid before its content lands on a parallel branch.

- **`retail` maps to exactly today's paths** (`pg_schema="public"`, bolt
  `NEO4J_BOLT_URI` or 7687), so the default path is byte-for-byte unchanged.
- **`shinhan`** is a self-contained bundle under `source/datasets/shinhan/`,
  `pg_schema="tn_shinhan"`, bolt default `bolt://localhost:7688` overridable via
  `NEO4J_BOLT_URI_SHINHAN`.

**Neo4j: instance-per-dataset.** Because arbitrary Cypher can't be tenant-scoped
reliably, each dataset gets its own Neo4j instance (retail 7687, shinhan 7688 via
a new `neo4j-shinhan` compose service). `knowledge_graph.compile --dataset <key>`
reads that dataset's bundle and writes to that instance; the full-wipe
`DETACH DELETE` stays safe precisely because isolation is per instance — wiping
one never touches another. This follows the build-artifact pattern of ADR 0005.

**Postgres: schema-per-dataset, retail == `public`.** A non-default dataset runs
the SAME Alembic chain (ADR 0010) into its own schema: `governance.pg.migrate`
creates the schema if absent and sets `TN_PG_SCHEMA`, which `env.py` reads to set
`version_table_schema` and the connection `search_path` so the plain DDL and
Alembic's own `alembic_version` both land in the dataset's schema. Runtime
connections `SET search_path` to the dataset schema. retail passes no schema
override, so its existing `public` tables and `alembic_version` are left exactly
as they were — the zero-churn requirement. Alembic stays a deploy-time-only import
(ADR 0010): the runtime CLI still never loads SQLAlchemy.

**CLI: a global `--dataset` option** on `tn`, threaded through `_run` into every
service call and the audit write. Unknown key → a clean `UNKNOWN_DATASET` envelope
(exit 1, valid JSON on stdout, message names the valid keys) — caught centrally in
`_run` before any store is touched, never a traceback. Adding the option is a
contract change: CONTRACT.md and a new golden (`unknown-dataset-error`) cover it;
existing goldens stay byte-identical and conformance stays green.

## Consequences

Adding a dataset is now a registry entry plus its content bundle — no new seams.
Isolation is structural (separate instance, separate schema), not a filter that
could be forgotten, so a cross-tenant leak would require a mis-registered path,
not a missing `WHERE`. The cost is operational: a second Neo4j instance to run
and compile, and a per-dataset loader/compile step (`--dataset shinhan`) to
provision before that dataset answers. A dataset queried before it is provisioned
fails with a clean `INTERNAL` envelope naming what's missing, never a stderr-only
traceback or invalid stdout. Cross-dataset queries remain a non-goal — the graph
and warehouse are per instance and never joined. retail is untouched by all of
this, which is what keeps the change safe to land under the existing gates.

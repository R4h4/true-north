# Architecture Decision Records

The immutable log of *why* true-north is built the way it is.

- One record per decision, numbered sequentially in `records/`.
- A record is a snapshot of a decision at a point in time. **Accepted records are
  not edited.** A change of direction is a new record that supersedes an old one.
- Use `template.md` as the starting point. Decisions that change the harness-facing
  interface additionally need a `CONTRACT.md` PR — the ADR records the why, the
  contract records the what.

## Index

- [0001](records/0001-single-governed-cli.md) — Single governed CLI as the only harness-facing interface
- [0002](records/0002-metrics-dsl-no-raw-sql.md) — Metrics DSL on the warehouse surface; no raw SQL
- [0003](records/0003-ambiguity-lives-in-the-graph.md) — Ambiguity lives in the graph; exact keys on the warehouse surface
- [0004](records/0004-stub-first-conformance-gated.md) — Stub-first delivery, conformance-gated; the stub dies at the gate
- [0005](records/0005-neo4j-docker-compose.md) — Real Neo4j via docker-compose, not an embedded engine
- [0006](records/0006-sqlglot-compiler.md) — SQL compiler builds SQLGlot ASTs
- [0007](records/0007-users-yaml-single-policy-source.md) — users.yaml is the single policy source; denials are derived
- [0008](records/0008-two-owner-agent-dev-process.md) — Two-owner development with frontier agents; thin process, no heavy harness
- [0009](records/0009-single-semantic-loader-seam.md) — One typed semantic loader in source; table semantics as YAML; KG tests on live; access single-sourced in governance.policy
- [0010](records/0010-postgres-policy-and-audit.md) — Runtime policy store + query audit in Postgres; authored YAML compiles into the store, same pattern as the graph
- [0011](records/0011-multi-dataset-architecture.md) — Multi-dataset (multi-tenant) via one registry seam; Neo4j instance-per-dataset, Postgres schema-per-dataset (retail=public), global `--dataset` flag defaulting to retail

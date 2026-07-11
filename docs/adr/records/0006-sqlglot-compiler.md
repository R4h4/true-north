# 0006 — SQL compiler builds SQLGlot ASTs

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

The semantic layer compiles metric definitions + role policy into DuckDB SQL: measure
aggregation, join resolution, row-filter predicate injection, projection
masking/tokenization/banding. Two options: hand-rolled string templates (zero deps,
byte-stable) or building ASTs with SQLGlot. The DSL is closed — inputs are validated
keys and canonical values, never user SQL — so injection risk was not the deciding factor.

## Decision

Build the compiled query as a SQLGlot AST and render with a fixed dialect
(`duckdb`) and normalized formatting. SQLGlot is also reused where the toolchain
needs to *read* SQL: the semantic validator extracts column references from measure
`expr` strings by parsing them.

## Consequences

Structural guarantees (quoting, precedence, composability of injected predicates) and
room for the filter grammar to grow without string surgery. Determinism is preserved by
fixed generation settings and asserted by the e2e suite (identical call → identical
`compiled_sql`). Cost: a dependency, and generated SQL is one step removed when
debugging — mitigated by `provenance.compiled_sql` exposing every compiled query.

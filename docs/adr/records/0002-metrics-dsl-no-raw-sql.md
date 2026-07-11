# 0002 — Metrics DSL on the warehouse surface; no raw SQL

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

The pitch is *governed* self-service BI: the demo dataset plants traps (metric polysemy,
returns in a separate table, B2B skew, weekly snapshot grain) that a text-to-SQL agent
falls into. A raw SQL surface would make governance a rewriting problem (parse arbitrary
SQL, inject predicates, mask projections) and reopen every trap the semantic layer
exists to close. Both sides discussed it; Phong initially wanted SQL for flexibility.

## Decision

The warehouse surface is `tn query --metric <exact key>` with governed dimensions,
filters over canonical vocabularies, and `--grain/--start/--end` — nothing else. Raw SQL
is ruled out for all roles. Governed definitions compile to SQL; the agent never writes SQL.

## Consequences

Governance is compile-time and provable per query; the traps are answered by
construction (`net_revenue` includes returns because its definition does). The agent's
flexibility moves to the KG rounds: it must resolve terms to exact keys first. Cost: no
ad-hoc analytics beyond the governed catalog — a feature at demo scope, a v2 question after.

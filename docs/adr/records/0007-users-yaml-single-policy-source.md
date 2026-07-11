# 0007 — users.yaml is the single policy source; denials are derived

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

Governance data could live in several places: per-metric access blocks in the semantic
YAML, a dedicated policy.yaml, role properties in the graph. Duplicated policy drifts,
and hand-authored denial lists rot the moment a metric's underlying columns change. A
separate `policy.yaml` was drafted and dropped when it turned out to duplicate what
`governance/fixtures/users.yaml` already carried.

## Decision

`governance/fixtures/users.yaml` is the one policy source: demo tokens/personas plus all
role grants against **physical objects** (readable tables, row-filter predicate templates
with `discloses_as`, masked/tokenized/transformed columns; schema in `governance/POLICY.md`).
Everything downstream is derived at compile time: metric denial = unreadable measure table
(`ACCESS_DENIED_TABLE`, precedence) or masked measure column (`ACCESS_DENIED_METRIC`);
dimension denial = masked source column; KG `_access` and `CAN_READ`/`CAN_COMPUTE` edges
are the same derivation projected into the graph.

## Consequences

Policy changes are one-file edits that propagate everywhere by rebuild; validator checks
one file against `schema.py`. Semantic YAML stays governance-free. Cost: nobody can
express a one-off exception ("deny this one metric explicitly") without modeling the
underlying column reality — accepted, that pressure keeps the model honest.

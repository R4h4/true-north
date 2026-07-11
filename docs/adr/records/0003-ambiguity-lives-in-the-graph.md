# 0003 — Ambiguity lives in the graph; exact keys on the warehouse surface

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

"Retention", "revenue", "basket size" each have multiple defensible calculations — the
core planted trap. Somewhere the system must represent that a business term is ambiguous
and force a clarifying question. Fuzzy resolution on the query surface (v0.1 had an
`AMBIGUOUS_CONCEPT` error) proved to be dead code: an exact-key surface can only say
not-found.

## Decision

Concept ambiguity is a *graph shape*: a parent `Concept` with `VARIANT_OF` children and
**no `MEASURED_BY` of its own**; each variant measures exactly one governed metric
(1:1, validator-enforced). The warehouse surface takes exact metric keys only;
`METRIC_NOT_FOUND` carries candidates as a fallback. The harness is expected to resolve
terms in its KG rounds and ask the user when it lands on a parent.

## Consequences

The clarifying question — the demo's money moment — is driven by data the harness can
rely on (contract invariant), not by prompt engineering. Adding a new ambiguous term is
authoring two YAML files, no code. Cost: the harness *must* do KG rounds before
querying; skipping them degrades to not-found errors, which is the intended failure mode.

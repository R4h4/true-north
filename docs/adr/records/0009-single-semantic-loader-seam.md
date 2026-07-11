# 0009 — One typed semantic loader in source; KG derivations single-sourced

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

Phase 4 built the semantic layer + SQL compiler (`source/` + `governance/`) and the
knowledge graph (`knowledge-graph/`) as two parallel work packages. Merging them exposed
four duplications at the seam, each a drift hazard the deterministic-checks philosophy
(ADR 0008) is meant to prevent:

- **Two semantic parsers.** `governance/governance/semantic.py` had a typed loader
  (Measure/Metric/Dimension/SemanticLayer); `knowledge_graph/loaders.py` re-parsed the
  same `source/semantic/*.yml` into raw dicts with its own measure-column/measure-table
  helpers. Two models of the same files.
- **Table semantics as code.** `knowledge_graph/table_semantics.py` hand-maintained a
  dict of grain/freshness/description per table — authored data living in a Python module
  the source owner couldn't see or validate.
- **A frozen semantic snapshot.** `kg_tests/fixtures/semantic/` pinned a copy of the
  semantic layer so KG unit tests were stable against the other branch. It had already
  drifted from live.
- **Two access derivations.** `knowledge_graph/access.py` reimplemented the POLICY.md
  rules (table read, metric/dimension denial, precedence) that `governance/governance/
  policy.py` already owns (ADR 0007). Two copies of the same rules to keep in sync.

## Decision

Put the rigor at the seam; single-source each duplicated thing.

- **One typed loader, in the source package.** Promote the loader to `source`'s
  `semantic_layer` package (`true-north-source`). It is the semantic *model* and belongs
  with the package that owns the semantic YAML; source is already a dependency of
  governance, and knowledge-graph now depends on it too. governance and knowledge-graph
  both import it — no local copy, no re-export shim. `knowledge_graph.loaders` consumes
  the typed objects instead of re-parsing YAML.
- **Table semantics become authored YAML.** `source/semantic/tables/*.yml` (one file per
  physical table: `description`, `grain`, `freshness_note`), exposed as
  `SemanticLayer.tables`. The semantic-layer validator checks them (key resolves to a
  schema.py table, required fields present, every measure-referenced table has an entry);
  this replaces the compiler's runtime assert with a deterministic pre-commit check, with
  the `tables[key]` lookup in the compiler kept as a belt.
- **KG tests run on the live semantic layer.** The frozen snapshot is deleted; KG tests
  load `source/semantic/` through the shared loader. Node/edge counts changing when the
  authored YAML changes is now the intended, tested signal (a change detector, not a
  contract).
- **Access derivation single-sourced in governance.policy.** `knowledge_graph/access.py`
  becomes a thin adapter that projects `governance.policy.RoleAccess` results into the KG
  `_access` dicts and CAN_READ/CAN_COMPUTE edges — no rules reimplemented. `_access` is
  still computed at serialization time, never stored on nodes.

## Alternatives considered

- **A compiled manifest artifact** (source emits a JSON/graph manifest that governance and
  the KG consume) — rejected: adds a build-ordering step and an intermediate artifact to
  keep fresh, overhead not worth it on the hackathon timeline when a shared in-process
  loader gives the same single-source guarantee.
- **Loader stays in governance, source depends up into it** — rejected: inverts the layering
  (source is the lowest layer; the semantic model is source's own data), and would make the
  knowledge-graph depend on governance just to read the semantic layer.

## Consequences

One parser and one model for the semantic layer; table semantics and access rules each
have exactly one authored/derived home guarded by a deterministic check. `source` gains a
third published module and becomes a dependency of `knowledge-graph` (which also depends on
`governance` for the access adapter). We accept a slightly heavier dependency graph
(knowledge-graph → governance → source) for the removal of four drift surfaces. The replay
stub fixtures under `governance/fixtures/replay/` were intentionally left untouched (out of
this package's scope) and are now stale for the Dimension node shape, which gained a `type`
property per CONTRACT §4.1; they die at the conformance gate (ADR 0004).

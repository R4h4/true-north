---
phase: 2
title: "Mock Governed CLI & Conformance Tests"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: Mock Governed CLI & Conformance Tests

## Overview

A thin fake of the governed CLI that honors the Phase 1 contract, so the harness can be
built and demoed end-to-end before Karsten's real services exist. Plus the conformance
suite that later proves mock and real CLI are interchangeable.

## Requirements

- Functional: implements `whoami`, `graph`, `query` per contract; all 3 personas behave
  differently; permission denials and notices produced per `contracts/personas.json`.
- Non-functional: no Neo4j dependency (canned graph answers); realistic enough that
  swapping to the real CLI changes zero harness code (only the `GOVERNED_CLI_CMD` env var).

## Architecture

- `graph` surface: pattern-match incoming Cypher against a small fixture set (metric
  definitions, dimension lookups, permission metadata for the personas). **Fixtures must
  follow the KG schema frozen in the Phase 1 contract** — the agent's Cypher habits formed
  against the mock must survive contact with the real graph. Unknown-but-valid Cypher →
  "no results" success; malformed Cypher → `INVALID_QUERY` (golden example for both).
- `query` surface: the mock owns a ~20-line read-only DuckDB reader over
  `source/data/parquet/*.parquet` (generated **data** is the stable contract, defined by
  `schema.py`; do NOT import `source/` Python modules — Karsten refactors those internals
  in Phase 4, and a cross-fence import lets him break this mock without violating any
  fence rule). On top, apply demo governance from `personas.json`: row filter (province
  for `tok_hcmc_manager`), column masking per the contract's mask semantics (→ structured
  `notices`), table deny (`dim_customers` for `tok_analyst` → `PERMISSION_DENIED`).
- Conformance tests parametrized by `GOVERNED_CLI_CMD`, asserting the golden examples from
  `contracts/examples/` plus envelope/exit-code invariants. Same suite runs against the
  real CLI in Phase 4/6.

## Related Code Files

- Create: `harness/mock_cli/__init__.py`, `harness/mock_cli/__main__.py`,
  `harness/mock_cli/graph_fixtures.py`, `harness/mock_cli/governance_shim.py` (Python →
  snake_case)
- Create: `contracts/conformance/test_governed_cli_conformance.py` (joint-controlled path;
  Karsten reviews)
- Create: `harness/pyproject.toml` (uv workspace member, dep on duckdb)
- (Root `pyproject.toml` workspace members were pre-added in the Phase 1 session.)

## Implementation Steps

1. Scaffold `harness/` as a uv workspace member; verify `uv run python -m mock_cli --help`
   from `harness/`.
2. Implement token resolution from `contracts/personas.json` (`UNKNOWN_TOKEN` error path).
3. Implement the mock's own parquet reader + governance shim (filter/mask/deny +
   structured notices). Dev data: `cd source && uv run python -m generator.generate
   --scale tiny --seed 42` (seconds; no dependency on the demo-data plan's full-scale run).
4. Implement `graph` canned fixtures: enough Cypher patterns to cover metric lookup
   ("what does revenue mean" → gross/net/B2B caveats from TRAPS.md), dimension vocab
   (canonical channel/province values), and permission metadata per persona.
5. Write conformance suite against golden examples; run it: `GOVERNED_CLI_CMD="uv run
   python -m mock_cli" uv run pytest contracts/conformance/`.

## Success Criteria

- [ ] Conformance suite green against the mock.
- [ ] Same question via `tok_hcmc_manager` vs `tok_ceo` returns different row counts.
- [ ] `tok_analyst` querying `dim_customers` gets `PERMISSION_DENIED` with a helpful message.
- [ ] Karsten has reviewed the conformance suite (it constrains his Phase 4).

## Risk Assessment

- **Mock drifts from what Karsten builds** → the conformance suite is joint-controlled and
  is the definition of "compatible"; drift shows up as a red suite, not a demo-day surprise.
- **Canned Cypher too fake to exercise the agent** → acceptable: the agent's Cypher habits
  get tuned in Phase 6 against the real graph; fixtures only need to unblock loop
  development.

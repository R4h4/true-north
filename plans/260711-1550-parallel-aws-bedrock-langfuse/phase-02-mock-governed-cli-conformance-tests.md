---
phase: 2
title: "Stub CLI Fixtures & Conformance Tests"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: Stub CLI Fixtures & Conformance Tests

## Overview

**Resolved by Karsten's [PR #4](https://github.com/R4h4/true-north/pull/4)** (Typer
replay stub in `governance/`, conformance suite in `contracts/conformance/`, agent-dev
replay fixtures for three trap cycles + error paths, and `docs/USING-TN.md` as the
agent-facing guide). This phase is now Karsten's; Phong's remaining involvement is
**fixture-only PRs** to `governance/fixtures/replay/` when the harness needs scenarios
the stub doesn't cover (agreed: same-day rubber-stamp merges). The earlier ideas of a
Phong-owned mock or DSL-to-DuckDB compiler are dead — the requirements below stand as
the review checklist for PR #4.

## Requirements

- Functional: `pytest` conformance suite that runs every golden in `contracts/examples/`
  against whatever `GOVERNED_CLI_CMD` points at (stub now, real CLI later) and asserts
  envelope structure, error codes, exit codes (0/1/2), and typed
  `applied_permissions`/`permissions` objects — not row values.
- Functional: replay fixtures covering the agent-dev loop beyond the 10 goldens: the
  multi-round KG pattern (term → ambiguity parent → variants → metric + constraints via
  §4.4 canonical queries), one full `tn query` per demo trap question, and the
  self-correction paths (`METRIC_NOT_FOUND` + candidates, `INVALID_DIMENSION_VALUE` +
  `did_you_mean`).
- Non-functional: zero dependency on parquet/DuckDB/Neo4j — pure canned JSON; fixtures
  keyed by normalized command+args.

## Architecture

- `contracts/conformance/` (joint-controlled): pytest suite, parametrized by
  `GOVERNED_CLI_CMD` env var (default `uv run tn`). Structure asserts only — the
  contract's own rule (values are illustrative; asserting them breaks across dataset
  scales).
- Fixture contributions to the stub: JSON files following the golden format, proposed via
  PR into wherever the stub keeps its responses (Karsten's tree — so these are PRs, not
  direct pushes). Fixture content authored from CONTRACT.md §4.3's planted-ambiguity
  patterns (Retention variants, GMV gross vs net, basket size by items vs value).
- Personas: the four contract tokens (`tok-exec-mai`, `tok-rm-south-duc`, `tok-mkt-lan`,
  `tok-analyst-binh`); fixtures must show region-South `row_filter`, `column_banded`
  birth years, tokenized customer ids, and `ACCESS_DENIED_METRIC` with reason.

## Related Code Files

- Create: `contracts/conformance/test_governed_cli_conformance.py` (+ tiny
  `conftest.py` for the CLI-invocation helper)
- Create (via PR to Karsten's tree): stub replay fixtures for the trap questions + KG
  exploration rounds
- Modify: none of `source/`, `governance/`, `knowledge-graph/` directly

## Implementation Steps

1. Write the conformance runner: for each golden, invoke the CLI, compare envelope
   structure (keys, types, error code, exit code) with value-shape checks (e.g.
   `applied_permissions[].type` ∈ the four disclosure types).
2. Run it against the stub the moment PR #2's stub lands; report gaps to Karsten.
3. Author the agent-dev fixture set (trap questions × personas, KG rounds); PR them to
   the stub.
4. Wire `GOVERNED_CLI_CMD` default (`uv run tn`) into harness config so phase 3 starts
   against the stub with zero further setup.

## Success Criteria

- [ ] Conformance suite green against the stub; same suite later runs unmodified against
  the real CLI (phase 4 gate).
- [ ] Same trap question via `tok-rm-south-duc` vs `tok-exec-mai` shows a `row_filter`
  disclosure difference in fixtures.
- [ ] `tok-mkt-lan` requesting a margin metric replays `ACCESS_DENIED_METRIC` with the
  masked-column reason; an unknown metric replays `METRIC_NOT_FOUND` with candidates.
- [ ] Agent loop (phase 3) can complete a full KG-rounds → query → answer cycle for at
  least 3 trap questions purely on the stub.

## Risk Assessment

- **Stub ownership answer goes the other way** (Phong ships it) → scope grows by the
  replay engine (~a day); fixtures and conformance runner are identical either way, so
  nothing here is wasted.
- **Fixture PRs bottleneck on Karsten** → fixtures are additive JSON; agree in the
  phase-1 review that fixture-only PRs get same-day rubber-stamp merges.
- **Stub drifts from real CLI** → that's precisely what the conformance suite + shared
  goldens exist to catch; contract rule already requires goldens to update in the same PR
  as any contract change.

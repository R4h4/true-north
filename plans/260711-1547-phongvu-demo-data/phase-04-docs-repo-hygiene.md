---
phase: 4
title: "Docs & Repo Hygiene"
status: pending
priority: P2
dependencies: [3]
---

# Phase 4: Docs & Repo Hygiene

## Overview

Update `source/README.md` for the Path B outcome, decide the committed data state, and leave the repo in its convention-correct form (headers-only CSVs committed, generated data local-only and reproducible from seed).

## Requirements

- Functional: README documents the validated dataset (how it was produced, how to validate it, where the report lives); git state clean per repo convention.
- Non-functional: no changelog noise; docs only reflect user-visible behavior changes (new validation report + workflow), per documentation rules.

## Related Code Files

- Modify: `source/README.md`
- Create (done in Phase 3): `source/data/validation_report.md`
- Run: `source/generator/write_headers.py`

## Implementation Steps

1. Update `source/README.md`: add a short "Validation" subsection — the canonical demo dataset is `--scale full --seed 42`, trap-by-trap verification lives in `data/validation_report.md`, and the report must be regenerated after any generator change. Note the Path A evaluation outcome in one line (rejected per fabrication threshold; decision record in `plans/260711-1547-phongvu-demo-data/reports/`). No Path A source/license section is needed since no external data was used.
2. Decide committed state with the user-visible assumption from plan.md: keep repo convention — run `uv run python -m generator.write_headers` to reset `data/csv/` to headers-only before any commit; parquet stays gitignored. The demo machine keeps its generated data (regenerate CSVs afterward if the demo reads CSVs — it doesn't: query layer prefers parquet, which `write_headers` does not touch. Verify parquet files survive the reset).
3. Confirm `data/validation_report.md` is committed (it is documentation, not generated data) and is not matched by any gitignore rule.
4. Final check: `git status` shows only intended changes (README, validation_report.md, plan files); `uv run python -m query.cli --tables` still lists 8 tables (parquet-backed) after the CSV reset.

## Success Criteria

- [ ] README documents generation + validation workflow and the Path A decision in ≤10 added lines.
- [ ] `data/csv/` restored to headers-only; `data/parquet/` still holds full-scale data; query layer still serves all 8 tables.
- [ ] `validation_report.md` tracked by git; `git status` clean of stray generated files.
- [ ] Dates, paths, and claims in updated docs verified against the actual Phase 2/3 outputs.

## Risk Assessment

- Risk: resetting CSVs breaks the demo if anything reads CSVs directly. Mitigation: step 2 verifies the query layer serves from parquet after reset; if a consumer needs CSVs, regenerate locally (deterministic) without committing.
- Risk: committing multi-hundred-MB CSVs by accident. Mitigation: `write_headers` before commit is an explicit step; `git status` gate in step 4.
- Rollback: docs-only phase — `git checkout -- source/README.md`; data regenerable from seed at any time.

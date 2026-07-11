---
phase: 2
title: "Generate Dataset"
status: pending
priority: P1
dependencies: [1]
---

# Phase 2: Generate Dataset

## Overview

Run the existing deterministic generator (Path B) from `source/` in the tiny → small → full progression, ending with the demo dataset at `--scale full --seed 42`. No generator code changes expected.

## Requirements

- Functional: all 8 tables populated in `source/data/csv/` and `source/data/parquet/`; generation summary captured (row counts, date ranges).
- Non-functional: determinism preserved (`--seed 42` throughout); runtime and memory observed at each scale before committing to `full`.

## Architecture

Generator pipeline (existing, unchanged): `schema.py` TABLES → `generate.py` builds dims then facts day-by-day per store → writes CSVs to `data/csv/` (overwriting headers-only files) → converts each to Parquet with explicit Arrow schema in `data/parquet/`. Query layer prefers parquet over CSV per table.

## Related Code Files

- Run (no modification): `source/generator/generate.py`, `source/generator/write_headers.py`
- Output: `source/data/csv/*.csv`, `source/data/parquet/*.parquet` (8 tables each)

## Implementation Steps

All commands run from `source/` (uv-managed workspace member; deps install on first `uv run`).

1. Environment check: `uv --version`; then smoke test `uv run python -m generator.generate --scale tiny --seed 42` (seconds). Confirm the summary prints 8 tables with plausible row counts and date ranges `[2024-01-01..2025-12-31]` for sales.
2. Dev-scale run: `uv run python -m generator.generate --scale small --seed 42`. Record wall time and peak memory (`/usr/bin/time -l` on macOS). Extrapolate to full scale (~10× stores × ~7.5× baskets/day ≈ 60–75× small volume).
3. If extrapolation predicts unacceptable full-scale cost (>30 min wall or memory beyond machine limits), report to user with numbers before proceeding — do NOT silently rewrite the generator for performance (scope change).
4. Full run: `caffeinate -i uv run python -m generator.generate --scale full --seed 42` (run in background; expect multi-million sales lines). Capture the generation summary output.
5. Sanity-verify outputs: all 8 CSVs non-header-only, all 8 parquet files present; `uv run python -m query.cli --tables` lists 8 tables; `uv run python -m query.cli "SELECT count(*) FROM fact_sales_lines"` returns millions of rows.
6. Save the generation summary (row counts per table, date ranges, wall time) into the phase report at `plans/260711-1547-phongvu-demo-data/reports/full-scale-generation-run-log.md` for Phase 3/4 reference.

## Success Criteria

- [ ] Tiny and small runs complete cleanly with deterministic summaries.
- [ ] Full run completes; all 8 tables have data in both CSV and parquet.
- [ ] `query.cli --tables` shows all 8 tables; sales-line count is in the millions.
- [ ] Run log recorded (row counts, date ranges, wall time, memory).

## Risk Assessment

- Risk: full-scale run is slow/memory-heavy — facts are built as Python lists of dicts (~1M baskets × 1–2+ lines, plus B2B 8–30-line baskets). Mitigation: measure at small scale first (step 2/3 gate); generation is one-off and offline, so tens of minutes is acceptable if memory fits.
- Risk: interrupted run leaves partially written CSVs. Mitigation: rerun is idempotent (full overwrite per table); verify all 8 parquet files postdate the run.
- Risk: uv resolves different dependency versions than last tested. Mitigation: smoke test at tiny scale catches API breaks in seconds.
- Rollback: `uv run python -m generator.write_headers` restores the committed headers-only state at any point.

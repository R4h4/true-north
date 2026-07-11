---
title: "Phong Vu demo data: acquire or extend true_north warehouse dataset"
description: "Supply the 8-table dataset for the NL-to-SQL demo: bounded Path A (open data) decision, then Path B full-scale deterministic generation, trap-by-trap validation, and docs"
status: pending
priority: P2
branch: "main"
tags: [data, generator, duckdb, demo]
blockedBy: []
blocks: [260711-1550-parallel-aws-bedrock-langfuse]
created: "2026-07-11T08:50:16.896Z"
createdBy: "ck:plan"
source: skill
---

# Phong Vu demo data: acquire or extend true_north warehouse dataset

## Overview

Produce the demo dataset for the self-service BI / NL-to-SQL demo (Agentic AI Build Week, Retail track). The warehouse schema, deterministic generator, and read-only query layer already exist in `source/` and enforce all 8 traps from [TRAPS.md](../../source/data/TRAPS.md). Current data state is headers-only CSVs and empty parquet — data must be generated (or mapped).

Task mandate: Path A (map open retail data into the schema, time-boxed 45 min, reject if trap guarantees require fabricating >~40% of fact rows) with Path B (run/extend `source/generator/generate.py`) as default fallback.

**Pre-analysis from codebase read:** Path A rejection is near-certain by structure alone — every candidate source (Olist, UCI Online Retail II, M5) lacks returns, weekly inventory, promotions, and traffic entirely (3 of 4 fact tables 100% fabricated), and `fact_sales_lines` itself would need synthetic VND amounts, Vietnamese geography, canonical channels, category re-bucketing, B2B baskets, and walk-in NULLs. Phase 1 documents this decision with the fabrication math instead of skipping the mandate. Phases 2–4 execute Path B: generate at `--scale full --seed 42`, verify each trap with naive-vs-correct query pairs into `validation_report.md`, update README, and restore committed headers-only CSV state.

**No generator code changes are expected** — the existing generator already satisfies every trap guarantee. Extensions (new SKUs from phongvu.vn, extra seasonal events) are explicitly out of scope unless validation exposes a gap.

## Key Codebase Facts (verified 2026-07-11)

- `source/generator/schema.py` — single source of truth; 8 tables, canonical vocab (`CHANNELS`, `CANONICAL_PROVINCES`, `CATEGORIES`) match the task spec exactly.
- `source/generator/generate.py` — deterministic (single `np.random.default_rng(seed)`); scales tiny/small/full; traps 1–8 implemented (`build_stores` forces 2 mid-history openings + 1 closure; `_build_inventory` weekly Sundays lagging max sales date by 8 days; category return rates PC Component 0.11 vs Accessory 0.012; walk-in NULL probability 0.55 in-store).
- `source/query/engine.py` — read-only guard (single SELECT/WITH/DESCRIBE/SHOW/SUMMARIZE/EXPLAIN/FROM); parquet shadows CSV per table.
- History window fixed: 2024-01-01 → 2025-12-31. `HISTORY_END` is deterministic, not "today".
- Committed CSV state is headers-only; parquet is gitignored; `write_headers.py` resets CSVs.
- Full scale: 30 stores, 1,500 SKUs, 120k customers, 45 retail baskets/store/day → ~1M+ baskets, multi-million sales lines built as Python lists of dicts (runtime/memory risk — see phase 2).
- `fact_inventory` at full scale snapshots only the first 60 SKUs per store (documented generator choice; traps 5/6 still hold).

## Phases

| Phase | Name | Status |
|-------|------|--------|
| 1 | [Path Decision](./phase-01-path-decision.md) | Pending |
| 2 | [Generate Dataset](./phase-02-generate-dataset.md) | Pending |
| 3 | [Trap Validation](./phase-03-trap-validation.md) | Pending |
| 4 | [Docs & Repo Hygiene](./phase-04-docs-repo-hygiene.md) | Pending |

## Dependencies

Phases are strictly sequential: 1 → 2 → 3 → 4. This plan blocks `260711-1550-parallel-aws-bedrock-langfuse` (see frontmatter), which needs the validated dataset.

## Acceptance Criteria

- [ ] Path A/B decision recorded with fabrication-share evidence against the ~40% threshold.
- [ ] `source/data/csv/*.csv` and `source/data/parquet/*.parquet` populated for all 8 tables at `--scale full --seed 42`.
- [ ] `uv run python tests/test_query_layer.py` passes; `query.cli --tables` lists all 8 tables.
- [ ] `source/data/validation_report.md` documents FK integrity plus a naive-vs-correct query pair per trap (all 8), with actual result values.
- [ ] `WHERE channel='offline'` and `WHERE province='HCMC'` each return 0 rows (trap 7 explicit check).
- [ ] README updated (generation + validation instructions); committed CSV state restored to headers-only.

## Assumptions (per task's "note the assumption" rule)

1. `validation_report.md` lives at `source/data/validation_report.md`, beside `TRAPS.md` which it verifies. The task lists it without a path.
2. Deliverable "generated CSVs/parquet" means present on the demo machine, not committed — the repo convention (headers-only CSVs committed, parquet gitignored) stands, since `--seed 42` makes the data fully reproducible.
3. No generator extensions (phongvu.vn scraping, new seasonal events) — the demo needs data that satisfies the traps, which the generator already provides.

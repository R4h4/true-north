---
phase: 3
title: "Trap Validation"
status: pending
priority: P1
dependencies: [2]
---

# Phase 3: Trap Validation

## Overview

Verify against the full-scale generated data that every one of the 8 trap guarantees actually holds, plus FK integrity, using naive-vs-correct query pairs through the read-only query layer. Record queries and actual result values in `source/data/validation_report.md`.

## Requirements

- Functional: run `tests/test_query_layer.py`; run one naive + one correct query per trap; run FK anti-join checks; write the report with real numbers.
- Non-functional: all validation goes through `query.cli` (or `query.engine.run_query`) so the read-only guard is exercised; queries must be single statements (guard rejects multi-statement).

## Architecture

Each `query.cli` invocation creates an in-memory DuckDB connection with one view per table (parquet preferred). For the ~20 validation queries, a small throwaway driver script that calls `query.engine.connect()` once and `run_query()` per check is acceptable (keeps the guard in the loop, avoids re-scanning parquet metadata 20×); write it under the scratchpad, not the repo.

## Related Code Files

- Run: `source/tests/test_query_layer.py`, `source/query/cli.py` / `source/query/engine.py`
- Create: `source/data/validation_report.md` (assumption noted in plan.md: lives beside `TRAPS.md`; user-mandated deliverable)

## Validation Checks (query pairs, expected outcomes)

**Gate 0 — query layer + FK integrity**
- `uv run python tests/test_query_layer.py` → "all checks passed".
- Anti-joins, each expected 0: `fact_sales_lines.store_id/sku_id` → dims; `customer_id` (non-NULL) → `dim_customer`; `promo_id` (non-NULL) → `dim_promotion`; `fact_returns.orig_basket_id` → `fact_sales_lines.basket_id`; `fact_returns.sku_id` → `dim_sku`; `fact_inventory.store_id/sku_id` → dims; `fact_traffic.store_id` → `dim_store`.

**Trap 1 — metric polysemy.** Naive: `SUM(net_amount)` as "revenue". Correct trio: booked vs net-of-returns (`− SUM(fact_returns.refund_amount)`) vs retail-only (`channel <> 'b2b'`). Expect three materially different numbers; also show b2b share of value ≫ b2b share of basket count.

**Trap 2 — separate returns table.** Category ranking by `SUM(net_amount)` vs by `SUM(net_amount) − refunds`; expect at least one rank swap. Return rate per category: PC Component ≈ 11% (highest), Accessory ≈ 1.2% (lowest).

**Trap 3 — nullable customer_id.** `channel='b2b' AND customer_id IS NULL` → 0 rows. Share of `in_store` lines with NULL customer → meaningful (generator: ~55%). Loyalty penetration naive (inner join) vs correct (non-NULL over all lines) differ.

**Trap 4 — same-store comparability.** `dim_store WHERE opened_date >= DATE '2024-01-01'` → ≥2 rows (generator: days 150 and 400). `closed_date IS NOT NULL` → exactly 1 (day 520). Show naive total-YoY vs same-store-YoY diverge.

**Trap 5 — snapshot grain.** Naive `SUM(on_hand_qty)` vs correct latest-snapshot `SUM(on_hand_qty)`; naive should be ~N_weeks× larger. Confirm one row per store×sku×week (no duplicate `store_id, sku_id, snapshot_date`).

**Trap 6 — staleness.** `MAX(snapshot_date) < MAX(CAST(ts AS DATE))` with a lag of ~8 days (generator constant).

**Trap 7 — value-format.** `WHERE channel = 'offline'` → 0. `WHERE province = 'HCMC'` → 0. `WHERE province = 'Hanoi'` → 0. Positive controls: `channel IN ('in_store','web','app','b2b')` covers 100% of lines; `province = 'Ho Chi Minh City'` returns rows.

**Trap 8 — unit trap.** Per-SKU sample: `AVG(gross_amount/qty)` ≠ `list_price` and `AVG(cost_amount/qty)` ≠ `unit_cost` (jitter ±3%/±2%). Grand total `SUM(net_amount)/1e9` expressed in tỷ to demonstrate the scale convention.

## Implementation Steps

1. Run gate 0 (test suite + FK anti-joins). Any orphan FK is a generator bug: stop, report — do not hand-edit CSVs (guardrail).
2. Run the 8 trap query pairs above, capturing SQL + actual results.
3. Note the known coverage limitation in the report: at full scale `fact_inventory` snapshots the first 60 SKUs per physical store (generator design; traps 5/6 unaffected).
4. Write `source/data/validation_report.md`: one section per trap — guarantee, naive query + result, correct query + result, verdict; FK section; generation metadata header (scale, seed, generated-at, row counts from Phase 2 run log).
5. If any trap fails to hold in the data, the fix goes into `generate.py` (and `TRAPS.md` if trap-relevant), then regenerate — never post-hoc data edits. Treat as a scope escalation: report before changing the generator.

## Success Criteria

- [ ] `tests/test_query_layer.py` passes; all FK anti-joins return 0.
- [ ] All 8 traps verified with naive-vs-correct pairs showing the expected divergence.
- [ ] Trap 7 zero-row checks and positive controls both recorded.
- [ ] `source/data/validation_report.md` complete with actual values and generation metadata.

## Risk Assessment

- Risk: a trap holds "by design" but marginally at full scale (e.g., no category rank swap materializes). Mitigation: queries check the guarantee empirically; on failure, escalate per step 5 rather than weakening the check.
- Risk: multi-million-row anti-joins slow via repeated CLI invocations. Mitigation: single-connection driver script through `query.engine` (DuckDB handles this size trivially).
- Risk: report drifts from data after a regeneration. Mitigation: metadata header ties the report to scale+seed+timestamp; regenerating obliges re-running this phase.

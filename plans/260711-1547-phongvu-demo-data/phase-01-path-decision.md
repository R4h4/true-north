---
phase: 1
title: "Path Decision"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Path Decision

## Overview

Execute the task-mandated Path A evaluation as a bounded desk-check (≤45 min, expected ≤20 min) and record the A-vs-B decision with fabrication-share evidence. No dataset download is required unless the desk-check surprisingly passes the structural test — the rejection criterion ("fabricating more than ~40% of the fact rows") is decidable from the candidates' known schemas.

## Requirements

- Functional: a written decision record scoring each Path A candidate against the true_north schema and the 8 trap guarantees, concluding Path A or Path B.
- Non-functional: time-boxed; no Kaggle authentication, no downloads unless structurally justified; cite source schemas and licenses as publicly documented.

## Analysis to Verify and Record

Structural coverage of the 4 fact tables by each candidate:

| Fact table | Olist | UCI Online Retail II | M5/Walmart |
|---|---|---|---|
| `fact_sales_lines` | partial (order items; amounts BRL, geography Brazil, no channel/B2B/walk-in split) | partial (invoice lines; GBP, UK, no dims) | no line grain (daily unit sales) |
| `fact_returns` | absent | partial (negative-qty invoices, no reasons/refund structure) | absent |
| `fact_inventory` (weekly) | absent | absent | absent |
| `fact_traffic` (daily footfall) | absent | absent | absent (sales only, no footfall) |

Fabrication math to record: 3 of 4 fact tables must be 100% synthesized for every candidate, and the surviving `fact_sales_lines` mapping still requires synthetic VND amounts (electronics price bands), reassigned Vietnamese provinces, snake_case channels, 10-category re-bucketing, injected B2B baskets, and walk-in NULL patterns — i.e., the retained source signal is little more than timestamps and basket shapes. Fabricated share of fact rows ≫ 40% threshold → Path A rejected; Path B (existing generator) proceeds.

## Related Code Files

- Read: `source/generator/schema.py`, `source/generator/generate.py`, `source/data/TRAPS.md` (already verified — see plan.md Key Codebase Facts)
- Create: `plans/260711-1547-phongvu-demo-data/reports/path-a-vs-b-decision-record.md`

## Implementation Steps

1. Confirm the structural-coverage table above against publicly documented candidate schemas (from knowledge; quick web check only if uncertain on a specific point — stay inside the time box).
2. Compute and record the fabrication share per candidate (fraction of the 4 fact tables + row-level synthesis needed on `fact_sales_lines`).
3. Note licenses for the record (Olist: CC BY-NC-SA 4.0 — additionally problematic for a commercial demo; UCI ORII: CC BY 4.0; M5: competition terms).
4. Write the decision record to `reports/path-a-vs-b-decision-record.md`: candidates, coverage table, fabrication math, license notes, conclusion, and the exact rejection criterion quoted from the task.
5. If (unexpectedly) a candidate passes the 40% test, STOP and re-plan Phase 2 as a mapping pipeline instead of generation — this changes scope and needs user awareness.

## Success Criteria

- [ ] Decision record exists with per-candidate coverage table and fabrication-share reasoning.
- [ ] Explicit conclusion: Path A rejected / accepted, tied to the ~40% threshold.
- [ ] Total phase time ≤45 min.

## Risk Assessment

- Risk: over-investing in Path A exploration (downloading datasets) despite decisive structural evidence. Mitigation: desk-check only; the rejection criterion is quantitative and schema-level.
- Risk: decision looks pre-baked. Mitigation: record shows the math per candidate, not just the conclusion; step 5 keeps the door open if evidence contradicts the expectation.

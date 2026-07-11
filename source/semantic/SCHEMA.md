# Semantic-layer YAML schema

Internal spec (not contract) for the files under `source/semantic/`. The SQL compiler, the KG compile step, and the semantic-layer validator all consume these files; this document is what they agree on. Field names here are frozen — changing them means updating the validator tests in `tools/tests/` in the same PR.

Layout:

```
source/semantic/
  metrics/<key>.yml       one file per governed metric, filename = key
  dimensions/<key>.yml    one file per governed dimension, filename = key
```

## Metric file

```yaml
key: net_revenue                  # snake_case, unique, == filename
name: Net revenue
short_description: Revenue net of discounts and returns.   # one sentence, `tn metrics list`
description: >                    # full text, `tn metrics describe` + KG Metric node
  Booked revenue (net of line discounts) minus refunds from fact_returns. ...
concept: net-revenue              # KG variant-concept key that MEASURED_BY-links to this metric
type: derived                     # sum | count | ratio | derived
unit: VND                         # VND | ratio | count
version: "0.1"
formula: "SUM(net_amount) − SUM(refund_amount)"   # human-readable, for narration
time_dimension: date              # dimension key of type time; --grain/--start/--end bind here
dimensions: [channel, region, province, category]  # governed dimension keys (HAS_DIMENSION)
compute:
  measures:                       # named single-table aggregates
    sales_net:
      table: fact_sales_lines
      expr: net_amount            # SQL expression over the measure table's columns
      agg: sum                    # sum | count | count_distinct | avg
      time_column: ts             # column on `table` that --start/--end/--grain apply to
      filters: []                 # optional structured, always-applied: {column, operator, value}
      joins:                      # optional; how dimensions not on `table` are reached
        - {table: dim_store, left_on: store_id, right_on: store_id}
    returns_refund:
      table: fact_returns
      expr: refund_amount
      agg: sum
      time_column: return_date
      joins:
        - {table: fact_sales_lines, left_on: orig_basket_id, right_on: basket_id}
        - {table: dim_store, left_on: fact_sales_lines.store_id, right_on: store_id}
  expr: "sales_net - returns_refund"   # arithmetic over measure names; single measure name for simple metrics
```

Rules (enforced by the semantic-layer validator):

- `key` unique across metrics, equals filename stem, snake_case.
- Required: `key, name, short_description, description, concept, type, unit, version, formula, time_dimension, dimensions, compute`.
- `type` ∈ {sum, count, ratio, derived}; `unit` ∈ {VND, ratio, count}. `type: ratio` ⇒ `unit: ratio`.
- Every `compute.measures.*.table`, join table, `expr`/`filters`/`time_column`/join column reference resolves against `source/generator/schema.py` (`TABLES` — the single source of truth).
- `compute.expr` references only declared measure names; every declared measure is referenced.
- Every entry in `dimensions` is an existing dimension key; `time_dimension` is an existing dimension of `type: time`.
- Every metric key named in `CONTRACT.md` / `contracts/examples/` exists as a file (cross-layer check).

The metric's `tables[]` (contract: `metrics describe`, provenance, `COMPUTED_FROM`) are **derived** = the set of measure tables (join-only dim tables excluded). Governance is **never authored here** — denials derive from `governance/policy.yaml` (see `governance/POLICY.md`): a metric is denied to a role iff a measure `expr`/`filters` references a column masked for that role (→ `ACCESS_DENIED_METRIC`) or a measure table is not readable (→ `ACCESS_DENIED_TABLE`, which takes precedence).

## Dimension file

```yaml
key: channel
name: Sales channel
description: Transaction channel as recorded at point of sale.
type: categorical                 # categorical | time | geo | entity
source: fact_sales_lines.channel  # table.column; null only for type: time (virtual — bound per measure via time_column)
canonical_values: [in_store, web, app, b2b]   # required iff type: categorical; must match schema.py vocabularies
grains: [day, week, month, quarter, year]     # required iff type: time
```

Rules: `key` unique, equals filename stem; `source` resolves against `schema.py` (nullable for time); `canonical_values` exactly matches the corresponding vocabulary tuple in `schema.py` where one exists (CHANNELS, REGION values, CATEGORIES keys, …).

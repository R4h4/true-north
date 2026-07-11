# KG vocabulary YAML schema

Internal spec (not contract) for the files under `knowledge-graph/vocabulary/` — the **authored** half of the graph (glossary concepts, constraints). The compiled half (Metric, Dimension, Table, Role nodes and their edges) is generated from `source/semantic/` + `source/generator/schema.py` + `governance/policy.yaml` at compile time and is never authored by hand. Field names here are frozen — changing them means updating the validator tests in `tools/tests/` in the same PR.

Layout:

```
knowledge-graph/vocabulary/
  concepts/<key>.yml      one file per Concept node, filename = key
  constraints/<key>.yml   one file per Constraint node, filename = key
```

## Concept file

```yaml
key: net-revenue                 # kebab-case, unique, == filename
name: Net revenue
definition: >
  Revenue after discounts and returns — what finance recognises. ...
aliases: [revenue net of returns, actual revenue]
variant_of: gmv-revenue          # parent concept key; null for parents and standalone concepts
measured_by: net_revenue         # semantic-layer metric key; REQUIRED for variants, FORBIDDEN (null) for parents
```

Rules (enforced by the vocabulary validator — these encode the CONTRACT §4.2 invariants):

- `key` unique, kebab-case, equals filename stem. Required: `key, name, definition, aliases` (may be `[]`).
- **Variant** (non-null `variant_of`): `measured_by` required, resolves to an existing `source/semantic/metrics/<key>.yml`, and no two concepts share a `measured_by` target (1:1).
- **Parent** (some concept names it in `variant_of`): its own `measured_by` MUST be null — a parent with a metric would break the ambiguity signal the harness relies on.
- `variant_of` targets exist; no chains (a parent is never itself a variant); no self-reference.
- Aliases are unique **across all concepts** (case-insensitive), and no alias duplicates any concept `name`.

## Constraint file

```yaml
key: b2b_value_skew              # snake_case, unique, == filename (keys surface in provenance.constraint_keys)
statement: >
  ~5% of baskets are B2B and carry order values orders of magnitude above retail;
  averages over revenue metrics are skewed unless B2B is split out.
severity: warning                # info | warning | critical
constrains:                      # CONSTRAINS edge targets, `<kind>:<key>`
  - metric:net_revenue
  - metric:gmv_gross
  - table:fact_sales_lines
```

Rules: required `key, statement, severity, constrains` (non-empty); `severity` ∈ {info, warning, critical}; target kind ∈ {metric, dimension, table} with `metric:` keys resolving to semantic metric files, `dimension:` to semantic dimension files, `table:` to `schema.py` tables. Every trap in `source/data/TRAPS.md` should be carried by at least one constraint (checked as a warning, not an error — TRAPS.md is prose).

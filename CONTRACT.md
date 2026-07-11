# CONTRACT.md — the governed CLI interface (v0.1)

This file is the single source of truth for the interface between the `harness/` (Phong) and everything below it (Karsten). **Interface changes land only as PRs that edit this file.** If code and contract disagree, the contract wins and the code is a bug.

The harness consumes exactly one interface: the governed CLI (`tn`). Every call carries an auth token. The CLI fronts two surfaces:

1. **Knowledge graph** — Cypher (read-only) against Neo4j; permission metadata for the calling user is injected into answers.
2. **Warehouse** — governed metric queries (a DSL, not raw SQL) against the DuckDB warehouse, with the user's row/column/table permissions applied at compile time.

Invocation: `uv run tn <command> ...` from the repo root (a stub with canned responses ships first; same contract). All output is a single JSON envelope on stdout. Exit codes: `0` success, `1` handled error (envelope has `error`), `2` usage error.

---

## 1. Authentication

`--token <token>` is required on every command except `tn kg schema`. Tokens are static demo fixtures (no real auth — non-goal) resolving to a user + role. Canonical fixture file: `governance/fixtures/users.yaml`.

| Token | User | Role | Access summary |
|---|---|---|---|
| `tok-exec-mai` | Mai (CEO) | `executive` | All tables & metrics; PII tokenized |
| `tok-rm-south-duc` | Đức (Regional Manager South) | `regional_manager` | Row-filtered to `region = 'South'` on sales/traffic/inventory; PII masked |
| `tok-mkt-lan` | Lan (Marketing Ops) | `marketing_ops` | No `fact_inventory`; `cost_amount` masked (⇒ margin metrics denied); customer PII tokenized + birth_year banded |
| `tok-analyst-binh` | Bình (Data Analyst) | `data_analyst` | All tables & metrics; PII tokenized; no row filters |

`tn whoami --token T` returns the resolved user, role, and effective permissions (readable tables, row filters, masked/tokenized columns, denied metrics).

## 2. Output envelope

Every command returns:

```json
{
  "contract_version": "0.1",
  "ok": true,
  "user": {"id": "u_duc", "role": "regional_manager"},
  "result": { },
  "metadata": {
    "as_of": "2025-12-31",
    "applied_permissions": {
      "row_filters": ["dim_store.region = 'South'"],
      "masked_columns": ["dim_customer.province"],
      "tokenized_columns": ["fact_sales_lines.customer_id"]
    },
    "provenance": {
      "metric_key": "net_revenue",
      "metric_version": "0.1",
      "tables": ["fact_sales_lines", "fact_returns"],
      "compiled_sql": "SELECT ..."
    }
  },
  "warnings": [
    {"code": "STALE_DATA", "message": "fact_inventory latest snapshot is 2025-12-21, 10 days behind sales"}
  ],
  "error": null
}
```

- `result` shape is per-command (below). On `ok: false`, `result` is null and `error` is set.
- `applied_permissions` is **always present and truthful** — the agent narrates from it ("your view is scoped to region South"). Row-level security is disclosed, never silent.
- `provenance` present on warehouse queries; `compiled_sql` included so the harness can show its work.
- Monetary values are integer **VND**; the owning column metadata carries `"unit": "VND"`. Formatting (tỷ/billions) is the harness's job.

### Error codes

| Code | Meaning |
|---|---|
| `AUTH_INVALID_TOKEN` | Token unknown |
| `METRIC_NOT_FOUND` | No such metric key |
| `AMBIGUOUS_CONCEPT` | A name matched multiple governed metrics/concepts; `error.details.candidates` lists them (key, name, definition). The harness should ask the user, not guess |
| `ACCESS_DENIED_METRIC` | Metric exists but the role may not compute it; `error.details.reason` says why (e.g. "uses masked column cost_amount") |
| `ACCESS_DENIED_TABLE` | Cypher/DSL touched a table the role cannot read |
| `INVALID_DIMENSION` | `--group-by`/`--filter` used a dimension not governed for this metric |
| `INVALID_DIMENSION_VALUE` | Filter value not in the canonical vocabulary; `error.details.did_you_mean` (e.g. `"offline"` → `"in_store"`) |
| `QUERY_REJECTED` | Cypher write attempt / multi-statement / non-read DSL |
| `INVALID_QUERY` | Syntax error; message passes through the engine error |

**Existence vs. permission is always distinguishable**: not-found is `METRIC_NOT_FOUND`; exists-but-forbidden is `ACCESS_DENIED_*` with a reason. That distinction is a product feature, not a leak, for this demo.

## 3. Commands

### `tn whoami --token T`
`result`: `{user, role, readable_tables[], row_filters[], masked_columns[], tokenized_columns[], denied_metrics[]}`

### `tn metrics list --token T`
`result.metrics[]`: `{key, name, short_description, type, unit, access: {allowed: bool, reason}}` — metrics the role cannot compute still appear, with `allowed: false` and a reason.

### `tn metrics describe <key> --token T`
`result`: full definition — `{key, name, description, type (sum|count|ratio|derived), unit, formula (human-readable), tables[], dimensions[]: {key, name, type, description}, constraints[]: {key, statement}, concept: {key, name}, access}`. This is the primary way the harness learns descriptions and types; the KG mirrors the same keys.

### `tn dimensions list --token T` / `tn dimensions describe <key> --token T`
`result`: `{key, name, description, type (categorical|time|geo|entity), source (table.column), canonical_values[] (categorical only), grains[] (time only)}`.

### `tn query --token T --metric <key> [--group-by <dim>]... [--filter "<dim> = '<value>'"]... [--start D] [--end D] [--limit N]`
One metric per call (v1). `--group-by`/`--filter` accept only that metric's governed dimensions; time grain via the time dimension's grains (`--group-by month`). Filter values are validated against canonical vocabularies.
`result`: `{columns[]: {name, type, unit}, rows[][], row_count}` plus full `metadata.provenance` and `applied_permissions`.

### `tn kg schema`
No token needed. `result`: node labels with properties, relationship types with direction (`(:From)-[:REL]->(:To)`), and 4–5 canonical example queries (§4.4).

### `tn kg query --token T "<cypher>"`
Read-only Cypher, single statement (`CREATE|MERGE|SET|DELETE|CALL {write}` rejected → `QUERY_REJECTED`).
`result.records[]`: rows as returned by the query; any graph node serialized as `{_label, key, ...properties, _access}` where `_access: {readable: bool, reason?}` is computed **for the calling user** — e.g. a `Metric` node comes back with `_access: {readable: false, reason: "uses masked column cost_amount"}`. The graph never hides nodes; it annotates them.

## 4. Knowledge-graph data model

The KG follows the Nexus shape: a governed vocabulary (concepts, constraints) authored as YAML, plus everything defined in the semantic layer (metrics, dimensions, tables, permissions) **compiled into the graph at compile time** (v1: a build step, no live sync). Sources of truth:

- `source/semantic/*.yml` — metrics, dimensions → `Metric`, `Dimension`, `Table` nodes
- `governance/fixtures/users.yaml` — roles → `Role` nodes + permission edges
- `knowledge-graph/vocabulary/*.yml` — concepts, variants, constraints (glossary & business knowledge)

### 4.1 Node labels

| Label | Key properties | Meaning |
|---|---|---|
| `Concept` | `key, name, definition, aliases[]` | Glossary / business knowledge. Can be a **parent** of variant concepts |
| `Metric` | `key, name, description, type, unit, formula, version` | Governed metric, 1:1 with a semantic-layer definition |
| `Dimension` | `key, name, description, type, canonical_values[]` | Governed dimension |
| `Table` | `key (physical name), description, grain, freshness_note` | Warehouse table |
| `Constraint` | `key, statement, severity` | Caveat that scopes validity ("weekly snapshot — never sum across weeks") |
| `Role` | `key, description` | Permission principal |

### 4.2 Relationships

```
(:Concept)-[:VARIANT_OF]->(:Concept)        // retention types -> Retention
(:Concept)-[:MEASURED_BY]->(:Metric)        // variant concept -> exactly one governed metric
(:Metric)-[:HAS_DIMENSION]->(:Dimension)
(:Metric)-[:COMPUTED_FROM]->(:Table)
(:Dimension)-[:DEFINED_IN]->(:Table)
(:Constraint)-[:CONSTRAINS]->(:Metric|:Dimension|:Table)
(:Role)-[:CAN_READ]->(:Table)
(:Role)-[:CAN_COMPUTE]->(:Metric)
```

Rules the compiler enforces: every variant `Concept` has exactly one `MEASURED_BY`; a parent concept has **no** `MEASURED_BY` of its own (asking for the parent is what triggers `AMBIGUOUS_CONCEPT`); every `Metric` in the graph exists in the semantic layer with the same key.

### 4.3 The planted ambiguity pattern (deliberate traps)

Parent concepts fan out into variants that are each a different, defensible calculation — the harness must notice and ask:

- **Customer Retention** → *Repeat-purchase retention* (`repeat_purchase_rate_90d`), *Loyalty-member activity retention* (`member_active_rate_30d`)
- **GMV / Revenue** → *GMV, gross* (`gmv_gross`), *Net revenue* (`net_revenue`, net of returns)
- **Basket size** → *by items* (`basket_items_avg`), *by value* (`basket_value_avg`)

Constraints carry the dataset traps: B2B value skew on revenue metrics, weekly-snapshot grain on inventory, ≥13-months rule on same-store growth, staleness on `fact_inventory`.

### 4.4 Canonical Cypher examples (returned by `tn kg schema`)

```cypher
// resolve a business term to governed metrics (the ambiguity path)
MATCH (c:Concept) WHERE c.name =~ '(?i).*retention.*' OR any(a IN c.aliases WHERE a =~ '(?i).*retention.*')
OPTIONAL MATCH (c)<-[:VARIANT_OF]-(v:Concept)-[:MEASURED_BY]->(m:Metric)
RETURN c, v, m

// everything needed to query a metric correctly
MATCH (m:Metric {key: 'net_revenue'})
OPTIONAL MATCH (m)-[:HAS_DIMENSION]->(d:Dimension)
OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m)
OPTIONAL MATCH (m)-[:COMPUTED_FROM]->(t:Table)
RETURN m, collect(DISTINCT d) AS dims, collect(DISTINCT k) AS caveats, collect(DISTINCT t) AS tables

// what can this role see?  (the CLI injects _access on every node anyway)
MATCH (r:Role {key: 'marketing_ops'})-[:CAN_COMPUTE]->(m:Metric) RETURN m.key
```

## 5. Demo user fixtures

Canonical file: `governance/fixtures/users.yaml` (committed; tokens are fake by design). Summary of intent — each persona exists to demo one governance feature:

| Persona | Demonstrates |
|---|---|
| Mai, `executive` | Happy path: full access, still gets disclosed provenance/caveats |
| Đức, `regional_manager` (South) | **Row-level security**: same question, South-scoped answer, disclosed in `applied_permissions` |
| Lan, `marketing_ops` | **Column masking + denial with reason**: margin metrics `ACCESS_DENIED_METRIC` ("uses masked column cost_amount"); no inventory table; **tokenization + banding** on customer PII |
| Bình, `data_analyst` | **Tokenization**: full analytical access, stable `cust_tok_*` customer ids (joinable, not identifying) |

## 6. Non-goals (v1)

No real auth (static tokens), no write path anywhere, single metric per `tn query`, no raw-SQL surface for any role, no live semantic-layer→KG sync (compile step), single tenant, English-only interface. Canonical dimension values live in the graph and in `tn dimensions describe` — the harness never needs to guess value spellings.

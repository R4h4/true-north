# CONTRACT.md — the governed CLI interface (v0.3)

This file is the single source of truth for the interface between the `harness/` (Phong) and everything below it (Karsten). **Interface changes land only as PRs that edit this file and its golden examples in the same PR.** If code and contract disagree, the contract wins and the code is a bug.

Everything in this file is **normative**: the harness may rely on it, and nothing else. The golden request/response pairs in `contracts/examples/` are normative for **envelope structure and error codes** (row values are illustrative — asserting values would break across dataset scales). How the services behind the CLI are built (semantic-layer YAML, vocabulary files, the KG compile step, governance internals) is intentionally *not* specified here — see the service READMEs; none of it is stable interface.

The harness consumes exactly one interface: the governed CLI (`tn`). Every call carries an auth token. The CLI fronts two surfaces:

1. **Knowledge graph** — Cypher (read-only) against Neo4j; permission metadata for the calling user is injected into answers. The expected usage pattern is multi-round: the harness explores the graph (resolve terms → variants → metrics → constraints), holds what it learned in context, surfaces ambiguity to the user, and only then queries data.
2. **Warehouse** — governed metric queries (**the DSL — decided; there is no raw-SQL surface**) against the DuckDB warehouse, with the user's row/column/table permissions applied at compile time.

Invocation: `uv run tn <command> ...` from the repo root (a stub with canned responses ships first; same contract, same goldens). All output is a single JSON envelope on stdout; logs go to stderr. Exit codes: `0` success, `1` handled error (envelope has `error`, including `INTERNAL`), `2` usage error. A non-zero exit without a parseable envelope is a crash — treat as `INTERNAL`.

The Neo4j browser exposed by docker-compose is for **human exploration only** — permission annotations exist only through the CLI, and nothing observed over raw bolt is contractual.

---

## 1. Authentication & demo personas

`--token <token>` is required on every command except `tn kg schema`. Tokens are static demo fixtures (no real auth — non-goal). The tokens below and the **observable behavior** they produce are contract; the fixture file behind them (`governance/fixtures/users.yaml`) is implementation and may change shape without a contract PR.

| Token | Persona | Role | Observable behavior (what the harness will see) |
|---|---|---|---|
| `tok-exec-mai` | Mai, CEO | `executive` | Full metric/table access. `applied_permissions` still discloses tokenized customer ids. Happy path with full provenance |
| `tok-rm-south-duc` | Đức, Regional Manager South | `regional_manager` | Store-grained queries return **South-only** results, disclosed as a `row_filter` entry. Customer-PII-backed dimensions are denied |
| `tok-mkt-lan` | Lan, Marketing Ops | `marketing_ops` | `fact_inventory` → `ACCESS_DENIED_TABLE`; margin/cost metrics → `ACCESS_DENIED_METRIC` with a reason naming the masked column; customer birth years appear as 5-year bands (`column_banded`); customer ids tokenized |
| `tok-analyst-binh` | Bình, Data Analyst | `data_analyst` | Full access, no row filters; customer ids are stable tokens |

Guarantees: **tokens (`cust_tok_…`) are deterministic within a demo run — stable and joinable** (counts, distincts, and joins over tokenized columns work; the raw value is unrecoverable). **Masked values are never returned in any form** — a dimension backed by a column masked for the role is denied (`ACCESS_DENIED_DIMENSION`), not returned as `***` or null.

### `tn whoami --token T`

`result`:

```json
{
  "user": {"id": "u_duc", "name": "Đức", "role": "regional_manager"},
  "readable_tables": ["dim_store", "dim_sku", "..."],
  "denied_metrics": [{"key": "gross_margin", "reason": "uses masked column cost_amount"}],
  "permissions": [
    {"type": "row_filter", "table": "dim_store", "column": "region", "operator": "=", "value": "South", "display": "dim_store.region = 'South'"},
    {"type": "column_masked", "column": "dim_customer.province", "display": "dim_customer.province is masked"},
    {"type": "column_tokenized", "column": "fact_sales_lines.customer_id", "display": "customer ids are stable tokens"}
  ]
}
```

`permissions` entries are **typed objects** (types: `row_filter`, `column_masked`, `column_tokenized`, `column_banded`) with a `display` string for narration. The same objects appear as `applied_permissions` on query responses.

## 2. Output envelope

Every command returns:

```json
{
  "contract_version": "0.3",
  "ok": true,
  "user": {"id": "u_duc", "role": "regional_manager"},
  "result": { },
  "metadata": {
    "as_of": "2025-12-21",
    "freshness": {"fact_sales_lines": "2025-12-31", "fact_inventory": "2025-12-21"},
    "applied_permissions": [
      {"type": "row_filter", "table": "dim_store", "column": "region", "operator": "=", "value": "South", "display": "dim_store.region = 'South'"},
      {"type": "column_tokenized", "column": "fact_sales_lines.customer_id", "display": "customer ids are stable tokens"}
    ],
    "provenance": {
      "metric_key": "net_revenue",
      "metric_version": "0.1",
      "tables": ["fact_sales_lines", "fact_returns"],
      "constraint_keys": ["b2b_value_skew", "returns_reduce_gross"],
      "compiled_sql": "SELECT ..."
    }
  },
  "warnings": [
    {"code": "STALE_DATA", "message": "fact_inventory latest snapshot is 2025-12-21, 10 days behind sales"}
  ],
  "error": null
}
```

- `result` shape is per-command (§3). On `ok: false`, `result` is null and `error` is set: `{code, message, details}`.
- `metadata.applied_permissions` is **always present and truthful on `tn query` and `tn kg query`** — the agent narrates from it ("your view is scoped to region South"). Row-level security is disclosed, never silent. Entries are the typed objects of §1.
- `provenance` present on warehouse queries. `compiled_sql` is included so the harness can show its work. `constraint_keys` lists the constraints attached to the touched metrics/tables — keys only; the harness is expected to already hold their statements in context from its KG rounds (resolve via `tn kg query` if not).
- **Freshness**: tables can be differently stale by design. `metadata.freshness` gives max available date per touched table; `as_of` = the minimum of those. A `STALE_DATA` warning fires when they diverge. `tn kg query` responses carry `metadata.graph_compiled_at` instead.

### Scalar serialization

| Type | JSON | Notes |
|---|---|---|
| Money | integer | VND; owning column metadata carries `"unit": "VND"`. Guaranteed to fit exactly in an IEEE-754 double (\|n\| ≤ 2^53−1); the CLI errors rather than silently rounding if an aggregate would exceed it |
| Ratio | number | **0–1 fraction**, `"unit": "ratio"`; percent formatting is the harness's job |
| Count | integer | `"unit": "count"` |
| DATE | string | `"YYYY-MM-DD"` |
| TIMESTAMP | string | `"YYYY-MM-DDTHH:MM:SS"`, business-local time (Asia/Ho_Chi_Minh), no offset suffix |
| NULL | `null` | never `"NULL"`, never omitted-key |
| NaN / Infinity | `null` | plus a `warnings` entry |

### Error codes

| Code | Meaning | `details` |
|---|---|---|
| `AUTH_INVALID_TOKEN` | Token unknown | — |
| `METRIC_NOT_FOUND` | `--metric` is not an exact metric key | `candidates[]: {key, name, definition}` when the string resembles known concepts/metrics — surface them, don't guess |
| `ACCESS_DENIED_METRIC` | Metric exists but the role may not compute it | `reason` (human-readable, e.g. `"uses masked column cost_amount"`) |
| `ACCESS_DENIED_TABLE` | Cypher/DSL touched a table the role cannot read | `table`, `reason` |
| `ACCESS_DENIED_DIMENSION` | Group-by/filter on a dimension backed by a column masked for this role | `dimension`, `reason` |
| `INVALID_DIMENSION` | Dimension not governed for this metric | `metric_key`, `valid_dimensions[]` |
| `INVALID_DIMENSION_VALUE` | Filter value not in the canonical vocabulary | `did_you_mean` (e.g. `"offline"` → `"in_store"`) |
| `QUERY_REJECTED` | Cypher write attempt / multi-statement / non-read DSL | `reason` |
| `INVALID_QUERY` | Syntax error | engine message passed through |
| `INTERNAL` | Unexpected failure inside the CLI/services | `message` is safe to surface; nothing else guaranteed |

**Existence vs. permission is always distinguishable**: not-found is `METRIC_NOT_FOUND`; exists-but-forbidden is `ACCESS_DENIED_*` with a reason. That distinction is a product feature for this demo, not a leak. There is no fuzzy resolution on the warehouse surface — exact keys only; *concept* ambiguity is represented in the graph (§4.3) and expected to be handled there, across the harness's KG rounds.

## 3. Commands

### `tn whoami --token T`
See §1.

### `tn metrics list --token T`
`result.metrics[]`: `{key, name, short_description, type, unit, access: {allowed: bool, reason}}` — metrics the role cannot compute still appear, with `allowed: false` and a reason.

### `tn metrics describe <key> --token T`
`result`: `{key, name, description, type (sum|count|ratio|derived), unit, formula (human-readable), tables[], dimensions[]: {key, name, type, description}, constraints[]: {key, statement}, concept: {key, name}, access}`. Exact key only. Describing a denied metric succeeds (`ok: true`) with `access.allowed: false` — annotate, don't hide. This and the KG are the two ways to learn descriptions and types; they mirror the same keys.

### `tn dimensions list --token T` / `tn dimensions describe <key> --token T`
`result`: `{key, name, description, type (categorical|time|geo|entity), source (table.column), canonical_values[] (categorical only), grains[] (time only), access}`.

### `tn query --token T --metric <key> [--group-by <dim>]... [--grain day|week|month|quarter|year] [--filter "<dim> = '<value>'"]... [--start D] [--end D] [--limit N]`

- One metric per call (v1). `--metric` takes the **exact key**.
- `--group-by` takes governed dimension keys of that metric only. Time bucketing is NOT a group-by: `--grain` applies to the metric's time dimension and adds the corresponding time column to the result.
- `--filter` grammar (v1): `<dim> = '<value>'` and `<dim> IN ('<v1>', '<v2>', ...)` on categorical dimensions only; multiple filters combine with **AND**. Date ranges only via `--start`/`--end` (inclusive, `YYYY-MM-DD`) on the time dimension. Values are validated against canonical vocabularies.
- Determinism: rows are ordered by the grouped columns ascending (time column first when `--grain` is used). Default `--limit 1000`; hitting it adds a `ROW_LIMIT` warning.

`result`: `{columns[]: {name, type, unit}, rows[][], row_count}` plus full `metadata` (§2).

### `tn kg schema`
No token needed. `result`: node labels with properties, relationship types with direction (`(:From)-[:REL]->(:To)`), the graph invariants (§4.2), and the canonical example queries (§4.4).

### `tn kg query --token T "<cypher>"`
Read-only Cypher, single statement (`CREATE|MERGE|SET|DELETE|REMOVE` and write procedures rejected → `QUERY_REJECTED`).

`result.records[]`: rows keyed by the query's RETURN aliases. **Serialization is recursive** — the rules apply wherever a graph entity appears (top level, inside `collect(...)` lists, maps, or paths):

- **Node** → `{_label, key, ...properties}`; nodes labeled `Metric`, `Table`, or `Dimension` additionally carry `_access: {readable: bool, reason?}` computed **for the calling user**. Other labels (`Concept`, `Constraint`, `Role`) carry no `_access` — they are knowledge, not governed resources.
- **Relationship** → `{_type, _from, _to, ...properties}` (`_from`/`_to` are node keys).
- **Path** → `{nodes: [...], relationships: [...]}` using the rules above.
- Scalars, lists, maps → plain JSON (scalar rules of §2 apply).

The graph never hides nodes; it annotates them. A denied metric is *visible* with `_access.readable: false` and a reason — "this exists but you can't see it" is the intended answer shape.

## 4. Knowledge-graph data model

Governed vocabulary (concepts, constraints) plus everything defined in the semantic layer (metrics, dimensions, tables, roles/permissions) is compiled into one graph. How and when it is compiled is internal (see `knowledge-graph/README.md`); the labels, relationships, and invariants below are contract.

### 4.1 Node labels

| Label | Key properties | Meaning |
|---|---|---|
| `Concept` | `key, name, definition, aliases[]` | Glossary / business knowledge. Can be a **parent** of variant concepts |
| `Metric` | `key, name, description, type, unit, formula, version` | Governed metric, 1:1 with a semantic-layer definition |
| `Dimension` | `key, name, description, type, canonical_values[]` | Governed dimension |
| `Table` | `key (physical name), description, grain, freshness_note` | Warehouse table |
| `Constraint` | `key, statement, severity` | Caveat that scopes validity ("weekly snapshot — never sum across weeks") |
| `Role` | `key, description` | Permission principal |

### 4.2 Relationships & graph invariants

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

Invariants the harness may rely on:

1. A **variant** `Concept` has exactly one `MEASURED_BY` edge.
2. A **parent** `Concept` (target of `VARIANT_OF`) has **no** `MEASURED_BY` of its own — resolving a term to a parent means the question is ambiguous and the variants are the candidates.
3. Every `Metric` node's `key` also exists in `tn metrics list`, with identical descriptions/types.
4. Every metric's queryable dimensions are exactly its `HAS_DIMENSION` targets.

### 4.3 The planted ambiguity pattern (deliberate traps)

Parent concepts fan out into variants that are each a different, defensible calculation — the harness is expected to notice and ask the user:

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

// what can this role see?  (the CLI injects _access on every governed node anyway)
MATCH (r:Role {key: 'marketing_ops'})-[:CAN_COMPUTE]->(m:Metric) RETURN m.key
```

## 5. Non-goals (v1)

No real auth (static tokens), no write path anywhere, single metric per `tn query`, no raw-SQL surface for any role, no fuzzy metric resolution on the warehouse surface, no live semantic-layer→KG sync (compile step), single tenant, English-only interface. Canonical dimension values live in the graph and in `tn dimensions describe` — the harness never needs to guess value spellings.

## Changelog

- **0.3** — DSL confirmed as the only warehouse surface (raw SQL ruled out). `applied_permissions`/`whoami.permissions` become typed objects (conformance-testable). Scalar serialization table (DATE/TIMESTAMP/NULL/NaN). `INTERNAL` error code. Golden examples in `contracts/examples/` made normative for structure; contract PRs must update them. `graph_compiled_at` on KG responses. All four services pre-registered as uv workspace members.
- **0.2** — Normative-only rewrite: internals moved to service READMEs; `AMBIGUOUS_CONCEPT` dropped (exact-key surface, `METRIC_NOT_FOUND` + candidates; ambiguity lives in the graph); recursive Cypher serialization + `_access` scope; per-table freshness; number-safety; filter grammar, `--grain`, deterministic ordering; `ACCESS_DENIED_DIMENSION`; personas as observable behavior.
- **0.1** — Initial contract: commands, envelope, error semantics, KG data model, personas.

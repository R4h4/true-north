# Using the `tn` governed CLI (agent guide)

Audience: the harness agent (and its developers). Full spec: `/CONTRACT.md` (v0.3, normative). This guide is operational.

## Setup & invocation

```bash
uv sync          # once, from repo root
uv run tn <command> ...
```

Every command except `tn kg schema` requires `--token <token>`. Output is always **one JSON envelope on stdout** (logs on stderr). Exit codes: `0` success, `1` handled error (parse `error.code`), `2` usage error. Flag order never matters.

Tokens: `tok-exec-mai` (executive, full access) · `tok-rm-south-duc` (regional manager, rows filtered to South) · `tok-mkt-lan` (marketing, no inventory/cost) · `tok-analyst-binh` (analyst, full, tokenized ids).

## The intended loop

1. **Bootstrap once**: `tn kg schema` → node labels, relationships, graph invariants, canonical Cypher queries.
2. **Resolve the user's term** via `tn kg query` (canonical query #1). If it resolves to a **parent Concept with variants** (parent has no `MEASURED_BY` — that's the ambiguity signal), ask the user which variant they mean; don't guess.
3. **Load the metric's context** (canonical query #2): governed dimensions, constraints (caveats — keep them in context, you must narrate them), tables.
4. **Query data** with `tn query --metric <exact key>` — keys come from step 2/3, never guessed.
5. **Narrate from the envelope**: `metadata.applied_permissions` (always disclose row filters), `metadata.freshness`/`as_of` + any `STALE_DATA` warning, `provenance.constraint_keys` (cross-check against the constraints you loaded in step 3). Money is integer VND; ratios are 0–1 fractions.

## Error handling (self-correction)

| `error.code` | What to do |
|---|---|
| `METRIC_NOT_FOUND` | `details.candidates` lists possible metrics — surface them to the user, don't pick silently |
| `INVALID_DIMENSION_VALUE` | `details.did_you_mean` + `canonical_values` — retry with the canonical spelling |
| `INVALID_DIMENSION` | `details.valid_dimensions` — regroup by a governed dimension |
| `ACCESS_DENIED_METRIC` | Metric exists; role blocked by a masked column (`details.reason`). Tell the user it exists but is not accessible to them |
| `ACCESS_DENIED_TABLE` | Blocking resource is a table the role can't read (also used when a metric's table is unreadable — table precedence over metric) |
| `ACCESS_DENIED_DIMENSION` | Dimension backed by a masked column for this role |
| `QUERY_REJECTED` | Read-only surface — no Cypher writes, single statements only |
| `AUTH_INVALID_TOKEN` / `INTERNAL` | Bad token / unexpected failure (on the stub: usually an un-fixtured request, see below) |

## Stub mode (current state)

Until the real services land (phase 4), `tn` is a **replay stub**: only the fixtured requests below return answers; anything else returns `INTERNAL` with message "no replay fixture" (exit 1). Fixtures live in `contracts/examples/` (goldens) and `governance/fixtures/replay/`; fixture-only PRs adding more are welcome and cheap.

### Fixtured requests

**Bootstrap / identity / catalog**

```bash
tn kg schema
tn whoami --token tok-exec-mai            # also: tok-rm-south-duc, tok-mkt-lan, tok-analyst-binh, tok-nobody (error)
tn metrics list --token tok-exec-mai      # also: tok-rm-south-duc, tok-mkt-lan, tok-analyst-binh
tn metrics describe gross_margin --token tok-mkt-lan   # denied-but-visible example
```

**KG rounds — three trap cycles** (resolve → detail; exact Cypher as in CONTRACT §4.4):

```bash
# retention (tok-analyst-binh): '(?i).*retention.*' resolve -> parent + 2 variants
# revenue/GMV (tok-exec-mai):  '(?i).*(revenue|gmv).*'  resolve -> gross vs net variants
# basket     (tok-analyst-binh): '(?i).*basket.*'       resolve -> items vs value variants
tn kg query --token tok-analyst-binh "MATCH (c:Concept) WHERE c.name =~ '(?i).*retention.*' OR any(a IN c.aliases WHERE a =~ '(?i).*retention.*') OPTIONAL MATCH (c)<-[:VARIANT_OF]-(v:Concept)-[:MEASURED_BY]->(m:Metric) RETURN c, v, m"
# metric detail (dims + caveats + tables); fixtured for: repeat_purchase_rate_90d, basket_value_avg (binh), net_revenue (mai)
tn kg query --token tok-analyst-binh "MATCH (m:Metric {key: 'repeat_purchase_rate_90d'}) OPTIONAL MATCH (m)-[:HAS_DIMENSION]->(d:Dimension) OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) OPTIONAL MATCH (m)-[:COMPUTED_FROM]->(t:Table) RETURN m, collect(DISTINCT d) AS dims, collect(DISTINCT k) AS caveats, collect(DISTINCT t) AS tables"
# access annotation example (lan): net_revenue readable, gross_margin _access.readable=false
tn kg query --token tok-mkt-lan "MATCH (m:Metric) WHERE m.key IN ['net_revenue','gross_margin'] OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) RETURN m, collect(k) AS caveats"
```

**Data queries**

```bash
tn query --token tok-analyst-binh --metric repeat_purchase_rate_90d --group-by channel
tn query --token tok-analyst-binh --metric basket_value_avg --group-by channel
tn query --token tok-exec-mai      --metric net_revenue --group-by channel   # national
tn query --token tok-rm-south-duc  --metric net_revenue --group-by channel   # South-filtered, row_filter disclosed
tn query --token tok-rm-south-duc  --metric net_revenue --group-by channel --start 2025-01-01 --end 2025-12-31
```

**Error paths (for testing self-correction)**

```bash
tn query --token tok-exec-mai     --metric revenue                          # METRIC_NOT_FOUND + candidates
tn query --token tok-analyst-binh --metric retention                        # METRIC_NOT_FOUND + candidates
tn query --token tok-exec-mai     --metric net_revenue --filter "channel = 'offline'"  # INVALID_DIMENSION_VALUE + did_you_mean
tn query --token tok-mkt-lan      --metric gross_margin --group-by category # ACCESS_DENIED_METRIC (masked column)
tn query --token tok-mkt-lan      --metric inventory_days                   # ACCESS_DENIED_TABLE (unreadable table)
tn kg query --token tok-analyst-binh "CREATE (m:Metric {key: 'fake'}) RETURN m"  # QUERY_REJECTED
```

## Conformance

`contracts/conformance/` runs every golden against whatever `GOVERNED_CLI_CMD` points at (default `uv run tn`): `uv run pytest contracts/conformance`. The same suite is the acceptance gate for the real CLI.

---
phase: 1
title: "Interface Contract & Workfences"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Interface Contract & Workfences

## Overview

Half-day joint session that produces the frozen governed-CLI contract and the repo working
agreement. This is the only phase where both people must be in the same (virtual) room;
everything after runs in parallel.

## Requirements

- Functional: a written, example-rich spec of the governed CLI both surfaces; a committed
  token→persona fixture; documented repo ownership + git rules.
- Non-functional: spec small enough to hold in one head (~2 pages); every behavior
  demonstrated by a concrete request/response example.

## Architecture

The governed CLI is invoked as a subprocess (harness side) with this proposed shape —
adjust in-session, then freeze:

```bash
governed-cli --token TOKEN whoami                 # → persona + permissions JSON
governed-cli --token TOKEN graph  "<cypher>"      # → knowledge-graph surface
governed-cli --token TOKEN query  "<select-sql>"  # → warehouse surface (read-only)
```

JSON envelope on stdout, exit code 0/1, logs to stderr:

```json
{"ok": true,  "user": "hcmc_manager", "data": {"columns": ["..."], "rows": [["..."]]}, "notices": ["column customer_name masked"]}
{"ok": false, "user": "hcmc_manager", "error": {"code": "PERMISSION_DENIED", "message": "table dim_customers not accessible; metric exists but uses it"}}
```

Error codes (closed set): `PERMISSION_DENIED`, `INVALID_QUERY`, `UNKNOWN_TOKEN`,
`INTERNAL`. `notices` is how governance tells the agent what was silently
filtered/masked — the harness surfaces these in answers.

**The contract MUST also freeze these surfaces** (red-team finding: these are exactly
where mock/real divergence would surface silently on integration day):

- **KG schema**: node labels, relationship types, and property names the agent may write
  Cypher against (e.g. `(:Metric {name, definition, caveat})-[:USES]->(:Table)`,
  `(:Persona)-[:CAN_ACCESS]->(:Table)`). The LLM authors Cypher live — an unfrozen graph
  schema means every agent query returns empty against the real graph. Karsten owns the
  ingest internals, but the queryable shape is contract.
- **`graph` result shape**: Cypher returns rows of maps/values, not warehouse columns —
  give it its own envelope example.
- **Serialization**: JSON types for DECIMAL (string vs number), DATE/TIMESTAMP (ISO 8601),
  NULL — DuckDB and Neo4j both bite here.
- **Exit codes**: `0` for any well-formed response including `ok:false` errors; non-zero
  only for crashes. (Alternative — nonzero on `ok:false` — fine too, but pick one.)
- **Mask semantics per persona**: "masked" = replaced with stable token (`CUST_8f3a`),
  dropped column, or `***`? Define per persona; the phase-02 shim currently conflates
  CEO ("PII masked") with analyst ("no PII columns").
- **`notices` structure**: machine-readable, e.g.
  `{"type": "column_masked", "column": "customer_name"}` — free prose can't be
  conformance-tested.
- **SQL vs DSL for `query` is decided in this session, not deferred** — the LLM authors
  the queries, so tool specs and the system prompt are rework if this lands late.

Personas (fixture `contracts/personas.json`, static tokens are fine — this is a demo):

| Token | Persona | Governance behavior to demo |
|---|---|---|
| `tok_ceo` | CEO | full rows, PII masked |
| `tok_hcmc_manager` | HCMC store manager | row-level: only `Ho Chi Minh City` stores |
| `tok_analyst` | Analyst | no PII columns, no `dim_customers` table access |

## Related Code Files

- Create: `docs/governed-cli-contract.md` (the spec: commands, envelope, error codes,
  personas, permission semantics, changelog section)
- Create: `contracts/personas.json` (token → persona → permissions)
- Create: `contracts/examples/` (golden request/response pairs, one per command × outcome)
- Modify: `README.md` (ownership table + git rules from plan.md "Parallel-Work Rules";
  mark governed CLI spec as "defined, see docs/governed-cli-contract.md")

## Implementation Steps

1. **Before the session** (Phong, ~1h): pre-draft the full contract text from the shapes
   above, including defaults for every "MUST freeze" bullet. The session ratifies a draft;
   it does not design from a blank page — that's how the 3h timebox holds.
2. Joint session (timebox 3h): walk the draft; decide the contested points — CLI name,
   raw SQL vs semantic-layer DSL for `query` (Karsten's call since he owns the DSL; if
   DSL, add a `metrics`/`dimensions` discovery subcommand), and the KG schema shape.
3. Write `docs/governed-cli-contract.md`; both commit-approve the same PR.
4. Commit `contracts/personas.json` + golden examples. Golden examples assert **envelope
   structure and error codes**, not row values — value asserts would break when dataset
   scale changes between laptops (tiny) and the demo box (full).
5. Add ownership/workflow section to README. No branch protection / CODEOWNERS — it only
   gates PRs while the workflow is push-to-main; for 2 people the fence is a social
   contract, enforced by the `git log --stat` spot-check.
6. Also pre-add all four services (`source`, `governance`, `knowledge-graph`, `harness`)
   as uv workspace members in root `pyproject.toml` **in this session** — kills the most
   likely day-1 merge conflict on a joint-controlled file.

## Success Criteria

- [ ] Spec merged with both owners' approval; changelog section present.
- [ ] `contracts/personas.json` + at least 6 golden examples committed (3 commands × ok/error).
- [ ] README documents ownership fences and the `uv.lock` conflict rule.
- [ ] Both tracks can state "what I build next" without asking the other anything.

## Risk Assessment

- **Raw SQL vs DSL lands late** → not acceptable to defer: the LLM *authors* the query
  strings, so tool descriptions and the system prompt depend on the choice. If truly
  deadlocked, contract v0 = raw SQL (matches the existing read-only engine) and a DSL
  becomes v1 with a planned prompt/toolspec rework budgeted.
- **Spec bikeshedding blows the timebox** → the pre-drafted text is the default;
  silence = accepted.

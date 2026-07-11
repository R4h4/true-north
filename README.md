# true-north

Governed self-service BI, built as a hackathon project: business users ask questions in natural language; an agent answers from a governed semantic layer with permissions, provenance, and a knowledge graph — instead of guessing SQL against raw tables.

The demo warehouse models **Phong Vũ** (phongvu.vn), a Vietnamese consumer-electronics retailer, as a synthetic star schema with deliberately planted traps a naive text-to-SQL agent falls into (see `source/data/TRAPS.md`).

## Architecture

```
        ┌─────────────────────────────────────────────────┐
        │                 harness  (Phong)                │
        │           LLM agent · chat interface            │
        └───────────┬─────────────────────────┬───────────┘
                    │ Cypher                  │ governed query CLI
                    │                         │ (auth token → user → permissions)
        ┌───────────▼───────────┐  ┌──────────▼───────────┐
        │    knowledge-graph    │  │      governance      │
        │  Neo4j: glossary +    │  │  row-level security  │
        │  business knowledge;  │  │  column anonymization│
        │  ingests metrics/dims │  │  PII tokenization    │
        │  incl. permission     │  │  table access        │
        │  metadata             │  │                      │
        └───────────┬───────────┘  └──────────┬───────────┘
                    │ ingests semantic layer  │ queries
        ┌───────────▼─────────────────────────▼───────────┐
        │                     source                       │
        │   DuckDB warehouse mock · semantic layer with    │
        │   governed metrics & dimensions · DSL/CLI        │
        └──────────────────────────────────────────────────┘
```

## Services

| Service | Owner | Responsibility | Interface (planned) |
|---|---|---|---|
| `source/` | Karsten | Mocked data warehouse (DuckDB) + semantic layer providing governed metrics & dimensions | DSL / CLI |
| `governance/` | Karsten | Row-level access security, column-level anonymization, PII tokenization, table access — applied per user | Authenticated query CLI (auth token resolves the user and their permissions) |
| `knowledge-graph/` | Karsten | Glossary + business knowledge; automatically ingests everything defined in the semantic layer (metrics, dimensions) **including permission metadata**, so answers can say "this metric exists but you don't have access" | Cypher (Neo4j) |
| `harness/` | Phong | The agent on top: queries the knowledge graph for context, then the warehouse through the governed CLI | Chat |

The two interfaces the harness consumes are the contract: **Cypher over the knowledge graph** (permission-aware answers) and the **governed query CLI** (auth-token-scoped data access). Exact interface specs are the next step — nothing beyond `source/` is implemented yet.

## Working in the repo

Python services are managed with **uv** as a workspace; run commands from inside a service directory:

```bash
cd source
uv run python -m generator.generate --scale small --seed 42   # build demo data
uv run python -m query.cli "SELECT count(*) FROM fact_sales_lines"
```

See `source/README.md` for the dataset and generator details, `docs/phongvu-domain.md` for the domain research.

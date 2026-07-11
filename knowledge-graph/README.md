# knowledge-graph

Business knowledge graph on Neo4j. Owner: Karsten. **Not started — interface spec is the next step.**

Contains:

- **Glossary & business knowledge** — concepts, definitions, caveats
- **Semantic-layer ingest** — every governed metric and dimension defined in `source/`'s semantic layer is automatically pulled in, so the graph always reflects what is actually queryable
- **Permission metadata** — access information rides on the graph, so an answer can be "this metric exists, but it uses a table you don't have access to" instead of silently omitting it

Interface: **Cypher, via the governed CLI** — not a raw Neo4j endpoint. The CLI call carries the auth token, which is what lets permission metadata be injected into graph answers for that user. The `harness/` queries this first to resolve business language into governed metrics/dimensions (and to learn what the user is allowed to see) before touching the warehouse. The Neo4j browser is for human exploration only; annotations exist only through the CLI.

## Internal design (not contract)

The graph is **compiled at build time** (v1: a build step, no live sync) from three sources of truth:

- `source/semantic/*.yml` — metrics, dimensions → `Metric`, `Dimension`, `Table` nodes
- `governance/fixtures/users.yaml` — roles → `Role` nodes + `CAN_READ`/`CAN_COMPUTE` edges (denial derived from masked columns / unreadable tables)
- `knowledge-graph/vocabulary/*.yml` — concepts, variants, constraints (glossary & business knowledge)

The compiler enforces the graph invariants in `/CONTRACT.md` §4.2 (variant concepts have exactly one `MEASURED_BY`; parents have none; every `Metric` node exists in the semantic layer under the same key). File layouts and the compile pipeline may change freely — only the resulting labels, relationships, and invariants are contract.

## Bring-up & compile

Neo4j runs in docker (root `docker-compose.yml`, ADR 0005); the graph is a build
artifact — every compile is a full wipe-and-rebuild stamped `graph_compiled_at`.

```bash
docker compose up -d                         # Neo4j on bolt://localhost:7687, browser :7474
uv run python -m knowledge_graph.compile     # wipe + rebuild from the three sources of truth
```

The compile reads `source/semantic/`, so Agent A's semantic layer must be present
(checked out, need not be committed). It asserts the §4.2 invariants after loading and
exits non-zero if any is violated. Re-running is idempotent: two consecutive compiles
produce identical node/edge sets (`graph_compiled_at` excepted).

Connection defaults match docker-compose (`neo4j` / `true-north-dev`, `bolt://localhost:7687`);
override with `NEO4J_BOLT_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`.

## Python API (consumed by the `tn` CLI at integration)

`knowledge_graph.api` is the seam the governed CLI wires `tn kg schema` / `tn kg query` to:

- `get_schema() -> dict` — node labels, relationship patterns, §4.2 invariants, §4.4 canonical queries.
- `run_cypher(cypher: str, role: str) -> dict` — read-only Cypher for the calling role, with
  recursive node/relationship/path serialization and per-role `_access` on `Metric`/`Table`/`Dimension`
  nodes (CONTRACT §3). Write clauses raise `QueryRejected`; syntax errors raise `InvalidQuery`.

`_access` derivation lives in `knowledge_graph.access` (mirrors `governance/POLICY.md`);
it is reconciled with `governance.policy` at integration — the e2e suite guards drift.

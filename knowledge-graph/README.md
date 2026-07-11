# knowledge-graph

Business knowledge graph on Neo4j. Owner: Karsten. **Not started — interface spec is the next step.**

Contains:

- **Glossary & business knowledge** — concepts, definitions, caveats
- **Semantic-layer ingest** — every governed metric and dimension defined in `source/`'s semantic layer is automatically pulled in, so the graph always reflects what is actually queryable
- **Permission metadata** — access information rides on the graph, so an answer can be "this metric exists, but it uses a table you don't have access to" instead of silently omitting it

Interface: **Cypher** against Neo4j. The `harness/` queries this first to resolve business language into governed metrics/dimensions (and to learn what the user is allowed to see) before touching the warehouse.

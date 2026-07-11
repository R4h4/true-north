# harness

The agent on top. Owner: Phong. **Not started.**

Consumes the two interfaces the other services provide:

1. **Cypher over the knowledge graph** — resolve the user's business question into governed metrics, dimensions, caveats, and permission info
2. **Governed query CLI** (auth token) — execute the actual data queries against the warehouse, with the user's permissions applied

Everything above that — agent loop, context loading, chat UX, model choice — is this service's call.

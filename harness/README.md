# harness

The agent on top. Owner: Phong. **Not started.**

Consumes one interface: the **governed CLI** (every call carries an auth token that resolves to a user), with two surfaces:

1. **Cypher over the knowledge graph** — resolve the user's business question into governed metrics, dimensions, caveats, and permission info (permission metadata injected per the token)
2. **Data queries against the warehouse** — execute the actual queries, with the user's row/column/table permissions applied

Everything above that — agent loop, context loading, chat UX, model choice — is this service's call.

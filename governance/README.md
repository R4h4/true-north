# governance

Data-governance layer. Owner: Karsten. **Not started — interface spec is the next step.**

Responsibilities:

- **Row-level access security** — which rows a user may see (e.g. region-scoped managers)
- **Column-level anonymization** — masking columns per role
- **PII tokenization** — stable tokens in place of identifying values
- **Table access** — which tables a user may touch at all

Together with `source/`, exposes the **governed query CLI**: every call carries an auth token that resolves to a user, whose permissions are applied before results are returned. This CLI (not raw DuckDB) is what the `harness/` uses to query the warehouse.

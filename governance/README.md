# governance

Data-governance layer. Owner: Karsten. **Not started — interface spec is the next step.**

Responsibilities:

- **Row-level access security** — which rows a user may see (e.g. region-scoped managers)
- **Column-level anonymization** — masking columns per role
- **PII tokenization** — stable tokens in place of identifying values
- **Table access** — which tables a user may touch at all

Together with `source/`, exposes the **governed query CLI**: every call carries an auth token that resolves to a user, whose permissions are applied before results are returned. This CLI (not raw DuckDB) is what the `harness/` uses to query the warehouse.

## Internal design (not contract)

- **Fixtures**: `fixtures/users.yaml` defines users, roles, row filters, masked/tokenized columns. Only the tokens and observable behavior are contract (`/CONTRACT.md` §1); this file's structure is free to change.
- **Denial is derived, not authored**: a role cannot compute any metric that touches a masked column or an unreadable table. The contract only guarantees that `ACCESS_DENIED_*` errors carry a human-readable `reason`.
- **Permissions apply at compile time**: the CLI accepts a DSL, never raw SQL, so row filters are injected and projections restricted while generating SQL — no SQL parsing/rewriting layer.
- **Tokenization**: deterministic HMAC-based (`cust_tok_` + 12 hex chars), stable within a demo run so joins/counts work. Scheme is internal; stability is the contractual property.

# Governance policy schema (`governance/fixtures/users.yaml`)

Internal spec (not contract). `users.yaml` is the **single policy source**: demo users/tokens plus all role-level grants against physical objects. Everything the harness observes (denied metrics/dimensions, `applied_permissions`, `_access` on graph nodes) is **derived** from it at compile time — nothing downstream is authored. Per CONTRACT §1 the tokens and observable behavior are contract; this file's structure is internal, but its field names are frozen against the validator tests in `tools/tests/` — change both in the same PR.

Structure (see the file itself for the live values):

```yaml
users:                            # one entry per demo token
  - token: tok-rm-south-duc
    user_id: u_duc
    name: "Đức"
    title: "Regional Manager, South"
    role: regional_manager        # must be declared under roles:
    attributes: {region: South}   # interpolated into row_filter templates

roles:
  <role_key>:
    description: ...
    tables: all                   # `all` or explicit list of schema.py table names
    row_filters:                  # predicates injected into every compiled query touching `tables`
      - tables: [fact_sales_lines, fact_traffic, fact_inventory]
        predicate: "store_id IN (SELECT store_id FROM dim_store WHERE region = '{region}')"
        discloses_as: "dim_store.region = '{region}'"   # -> row_filter disclosure object
    masked_columns: [...]         # never returned in any form; backing metrics/dimensions DENIED
    tokenized_columns: [...]      # stable joinable tokens (see tokenization:)
    transformed_columns:          # value-preserving transforms, disclosed as column_banded etc.
      - {column: dim_customer.birth_year, transform: band_5y}

tokenization: {scheme: hmac_sha256_prefix, prefix: cust_tok_, length: 12}
```

Validator rules: the four contract roles (`executive`, `regional_manager`, `marketing_ops`, `data_analyst`) all declared and the four contract tokens present, each user's `role` declared; every table/column reference resolves against `source/generator/schema.py`; `tables` is `all` or a subset of real tables; a column appears in at most one of masked/tokenized/transformed per role; every `{placeholder}` in a `predicate`/`discloses_as` template exists in the `attributes` of every user holding that role; `transform` ∈ {`band_5y`}.

Derivation rules (implemented in the compiler, asserted by the cross-layer check):

- **Metric denial**: a metric is denied to a role iff any of its measure tables is unreadable (→ `ACCESS_DENIED_TABLE`, precedence per CONTRACT) or any measure `expr`/`filters` column is masked (→ `ACCESS_DENIED_METRIC`, reason names the column). Tokenized/transformed columns do NOT deny — they disclose.
- **Dimension denial**: dimension's `source` column masked for the role → `ACCESS_DENIED_DIMENSION`.
- **KG `_access`**: `Metric`/`Table`/`Dimension` nodes get `readable` (+ `reason` when false) from the same derivation; `CAN_READ`/`CAN_COMPUTE` edges are its positive image.
- **Disclosure**: every row filter, tokenization, or transform that touched a query appears as a typed `applied_permissions` object (CONTRACT §1) — disclosed, never silent.

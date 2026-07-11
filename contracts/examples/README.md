# Golden request/response examples

One file per command × outcome. Each file holds the exact CLI invocation (`request.argv`) and the full expected envelope (`response`).

**Normative for envelope structure and error codes; row/aggregate VALUES are illustrative** — asserting values would break when dataset scale changes between laptops (tiny) and the demo box (full). Conformance = same keys, same types, same codes, same permission-object shapes.

Rules:

- Any PR that changes `/CONTRACT.md` updates the affected goldens in the same PR.
- The stub CLI and the real CLI must both satisfy every golden (structure-wise).
- `...` in a string value means "any string"; numeric values mean "any number of that JSON type".

Matcher conventions (what "structure match" means, exactly):

- **Exact-value fields**: `contract_version`, `ok`, `error.code`, `user.id`, `user.role`, and permission-object `type` (∈ `row_filter|column_masked|column_tokenized|column_banded`). The full sets of `applied_permissions`/`permissions`/`denied_metrics` objects are behavior, not data — they match exactly. Everything else matches by JSON type only; in particular, column/metric `type` enum values (`money`, `categorical`, `derived`, …) are illustrative.
- **Nullable siblings**: a `null` template scalar means the field is nullable — implementations may return `null` or a scalar of the type its non-null siblings show (e.g. `columns[].unit`).
- **Variant-shape lists**: homogeneous data lists (e.g. `rows`) match element shape against the first element. Lists of nodes/records with legitimately variant shapes (e.g. `_access.reason` present only on denied nodes) match **positionally** when the golden enumerates them.

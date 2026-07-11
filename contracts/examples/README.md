# Golden request/response examples

One file per command × outcome. Each file holds the exact CLI invocation (`request.argv`) and the full expected envelope (`response`).

**Normative for envelope structure and error codes; row/aggregate VALUES are illustrative** — asserting values would break when dataset scale changes between laptops (tiny) and the demo box (full). Conformance = same keys, same types, same codes, same permission-object shapes.

Rules:

- Any PR that changes `/CONTRACT.md` updates the affected goldens in the same PR.
- The stub CLI and the real CLI must both satisfy every golden (structure-wise).
- `...` in a string value means "any string"; numeric values mean "any number of that JSON type".

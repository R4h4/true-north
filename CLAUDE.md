# CLAUDE.md

1. Don't assume. Don't hide confusion. Surface tradeoffs.
2. Minimum code that solves the problem. Nothing speculative.
3. Touch only what you must. Clean up only your own mess.
4. Define success criteria. Loop until verified.

## Project layer

- `CONTRACT.md` is normative for the `tn` CLI; if code and contract disagree, the code is a bug. Contract changes only via PR that also updates `contracts/examples/`.
- Conformance/golden tests assert envelope structure and error codes, never row values.
- Python: uv workspace (`uv run`, `uv add`); tests: `uv run pytest` from repo root; source tests: `uv run python source/tests/test_query_layer.py`. Data: `cd source && uv run python -m generator.generate --scale small --seed 42` (CSV committed headers-only; parquet gitignored).
- Ownership: Karsten owns source/, governance/, knowledge-graph/; Phong owns harness/. Don't edit the other side's tree.
- Commit with explicit pathspecs (parallel sessions share this repo); every phase runs in a continuously-pushed draft PR.
- Deliberate dataset traps are documented in `source/data/TRAPS.md` — they are features, don't "fix" them.

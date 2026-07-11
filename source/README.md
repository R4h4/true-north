# source

Mocked data warehouse (DuckDB) + semantic layer with governed metrics & dimensions, exposed via a DSL/CLI. Owner: Karsten.

Today it contains the demo dataset (star schema modeling Phong Vũ) and a read-only query layer; the semantic layer / governed-metric DSL is next.

## Layout

```
generator/       # schema (single source of truth) + data generator
  schema.py         table -> ordered columns -> dtype + description
  write_headers.py  writes headers-only CSVs from schema.py
  generate.py       deterministic synthetic-data generator
query/           # read-only DuckDB layer: views over parquet (csv fallback), guard, CLI
data/csv/        # headers-only CSVs (committed); generator overwrites with data
data/parquet/    # generated parquet (gitignored)
data/TRAPS.md    # planted failure-mode traps and their correct handling
tests/           # self-contained checks (uv run python tests/test_query_layer.py)
```

## Generating data

Python is managed with **uv** (workspace member; run from this directory). Dependencies install automatically on first `uv run`.

```bash
uv run python -m generator.write_headers          # (re)write headers-only CSVs
uv run python -m generator.generate --scale tiny  --seed 42   # smoke test (seconds)
uv run python -m generator.generate --scale small --seed 42
uv run python -m generator.generate --scale full  --seed 42   # ~2y history, few M sales lines
```

The generator writes CSVs to `data/csv/` then converts each to Parquet in `data/parquet/`. The committed state of `data/csv/` is headers-only; run `write_headers.py` to reset after generating.

## Querying

```bash
uv run python -m query.cli --tables
uv run python -m query.cli --schema
uv run python -m query.cli "SELECT channel, sum(net_amount) FROM fact_sales_lines GROUP BY 1"
```

Read-only: single `SELECT`/`WITH`/`DESCRIBE`/`SHOW`/`SUMMARIZE`/`EXPLAIN` statements only.

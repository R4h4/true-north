# true_north

Demo-data foundation for a governed natural-language-to-SQL self-service BI system (hackathon project). The dataset models **Phong Vũ** (phongvu.vn), a Vietnamese consumer-electronics retailer, as a small star-schema warehouse with deliberately planted "traps" that a naive text-to-SQL agent falls into (metric polysemy, separate returns table, snapshot-grain double-counting, etc. — see `data/TRAPS.md`).

## Layout

```
generator/       # schema (single source of truth) + data generator
  schema.py         table -> ordered columns -> dtype + description
  write_headers.py  writes headers-only CSVs from schema.py
  generate.py       deterministic synthetic-data generator
data/csv/        # headers-only CSVs (committed); generator overwrites with data
data/parquet/    # generated parquet (gitignored)
docs/            # Phong Vũ domain research
```

## Generating data

Python is managed with **uv**. Dependencies install automatically on first `uv run`.

```bash
uv run python -m generator.write_headers          # (re)write headers-only CSVs
uv run python -m generator.generate --scale tiny  --seed 42   # smoke test (seconds)
uv run python -m generator.generate --scale small --seed 42
uv run python -m generator.generate --scale full  --seed 42   # ~2y history, few M sales lines
```

The generator writes CSVs to `data/csv/` then converts each to Parquet in `data/parquet/`. The committed state of `data/csv/` is headers-only; run `write_headers.py` to reset after generating.

"""Self-contained checks for the query layer (no pytest dependency yet).

Run: uv run python tests/test_query_layer.py

Builds its own fixture data dir, so it never races the generator's
writes to data/.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import duckdb

from query.engine import QueryError, connect, list_tables, run_query, schema_overview


def make_fixture(root: Path) -> Path:
    data = root / "data"
    (data / "csv").mkdir(parents=True)
    (data / "parquet").mkdir(parents=True)
    # header-only csv (pre-generation state)
    (data / "csv" / "dim_store.csv").write_text("store_id,store_name,format,region\n")
    # csv with rows, shadowed by a parquet with different content
    (data / "csv" / "fact_sales_lines.csv").write_text(
        "basket_id,sku_id,net_amount\nB1,S1,100\n"
    )
    duckdb.sql(
        "SELECT 'B9' AS basket_id, 'S9' AS sku_id, 250 AS net_amount"
    ).write_parquet(str(data / "parquet" / "fact_sales_lines.parquet"))
    return data


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        data = make_fixture(Path(tmp))
        conn = connect(data)

        assert list_tables(data) == ["dim_store", "fact_sales_lines"]

        # header-only csv -> empty view with the declared columns
        cols = [c for c, _ in schema_overview(conn)["dim_store"]]
        assert cols == ["store_id", "store_name", "format", "region"], cols
        assert run_query(conn, "SELECT count(*) AS n FROM dim_store").fetchone()[0] == 0

        # parquet shadows csv for the same table name
        row = run_query(conn, "SELECT basket_id, net_amount FROM fact_sales_lines").fetchone()
        assert row == ("B9", 250), row

        # read-only guard
        for bad in (
            "INSERT INTO dim_store VALUES (1,2,3,4)",
            "UPDATE dim_store SET region='x'",
            "DROP VIEW dim_store",
            "CREATE TABLE t (i INT)",
            "ATTACH ':memory:' AS other",
            "COPY dim_store TO 'out.csv'",
            "SELECT 1; SELECT 2",
            "  -- sneaky\nDELETE FROM dim_store",
            "",
        ):
            try:
                run_query(conn, bad)
            except QueryError:
                pass
            else:
                raise AssertionError(f"guard let through: {bad!r}")

        # comments and WITH are fine
        assert run_query(conn, "-- top line\nWITH x AS (SELECT 1 AS i) SELECT i FROM x").fetchone()[0] == 1

    print("query layer: all checks passed")


if __name__ == "__main__":
    main()

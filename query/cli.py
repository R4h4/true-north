"""CLI for the true_north query layer.

Usage:
    uv run python -m query.cli "SELECT count(*) FROM fact_sales_lines"
    uv run python -m query.cli --schema
    uv run python -m query.cli --tables
"""

from __future__ import annotations

import argparse
import sys

from .engine import QueryError, connect, list_tables, run_query, schema_overview


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="query", description="Read-only SQL over the true_north dataset.")
    parser.add_argument("sql", nargs="?", help="single read-only SQL statement")
    parser.add_argument("--schema", action="store_true", help="print all tables with columns and types")
    parser.add_argument("--tables", action="store_true", help="print table names")
    parser.add_argument("--max-rows", type=int, default=50, help="max rows to display (default 50)")
    args = parser.parse_args(argv)

    if args.tables:
        print("\n".join(list_tables()))
        return 0

    conn = connect()

    if args.schema:
        for table, cols in schema_overview(conn).items():
            print(f"\n{table}")
            for name, dtype in cols:
                print(f"  {name}  {dtype}")
        return 0

    if not args.sql:
        parser.print_help()
        return 2

    try:
        run_query(conn, args.sql).show(max_rows=args.max_rows)
    except QueryError as exc:
        print(f"rejected: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

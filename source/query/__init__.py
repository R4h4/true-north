"""DuckDB query layer for the true_north demo warehouse.

Read-only SQL over the generated dataset: Parquet files in data/parquet/
when present, falling back to the header-only CSVs in data/csv/ (which
yields empty views with the right columns before the generator has run).
"""

from .engine import QueryError, connect, list_tables, run_query, schema_overview

__all__ = ["QueryError", "connect", "list_tables", "run_query", "schema_overview"]

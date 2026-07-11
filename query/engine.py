"""Read-only DuckDB engine over the true_north dataset.

One view per table. Parquet (data/parquet/<table>.parquet) wins over CSV
(data/csv/<table>.csv); header-only CSVs produce empty views so the layer
works before any data has been generated.
"""

from __future__ import annotations

import re
from pathlib import Path

import duckdb

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA_DIR = REPO_ROOT / "data"

# First keyword of the single statement we are willing to execute.
_READONLY_STARTERS = ("select", "with", "describe", "show", "summarize", "explain", "from")

_COMMENT_RE = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)


class QueryError(ValueError):
    """Raised when a query is rejected by the read-only guard."""


def _discover_tables(data_dir: Path) -> dict[str, Path]:
    """Map table name -> backing file, preferring parquet over csv."""
    tables: dict[str, Path] = {}
    for csv in sorted((data_dir / "csv").glob("*.csv")):
        tables[csv.stem] = csv
    for pq in sorted((data_dir / "parquet").glob("*.parquet")):
        tables[pq.stem] = pq
    return tables


def list_tables(data_dir: Path | None = None) -> list[str]:
    return sorted(_discover_tables(data_dir or DEFAULT_DATA_DIR))


def connect(data_dir: Path | None = None) -> duckdb.DuckDBPyConnection:
    """In-memory connection with one view per discovered table."""
    data_dir = data_dir or DEFAULT_DATA_DIR
    conn = duckdb.connect(":memory:")
    for name, path in _discover_tables(data_dir).items():
        if path.suffix == ".parquet":
            reader = f"read_parquet('{path.as_posix()}')"
        else:
            reader = f"read_csv('{path.as_posix()}', header=true, auto_detect=true)"
        conn.execute(f'CREATE OR REPLACE VIEW "{name}" AS SELECT * FROM {reader}')
    return conn


def _guard(sql: str) -> str:
    stripped = _COMMENT_RE.sub(" ", sql).strip()
    if not stripped:
        raise QueryError("empty query")
    statements = [s for s in stripped.split(";") if s.strip()]
    if len(statements) != 1:
        raise QueryError("exactly one statement per query")
    first_word = statements[0].split(None, 1)[0].lower()
    if first_word not in _READONLY_STARTERS:
        raise QueryError(
            f"only read-only queries are allowed (got '{first_word}'); "
            f"start with one of: {', '.join(_READONLY_STARTERS)}"
        )
    return statements[0]


def run_query(conn: duckdb.DuckDBPyConnection, sql: str) -> duckdb.DuckDBPyRelation:
    """Execute a single read-only statement and return the relation."""
    return conn.sql(_guard(sql))


def schema_overview(conn: duckdb.DuckDBPyConnection) -> dict[str, list[tuple[str, str]]]:
    """table -> [(column, type), ...] for every view on the connection."""
    overview: dict[str, list[tuple[str, str]]] = {}
    tables = [r[0] for r in conn.execute("SELECT view_name FROM duckdb_views() WHERE NOT internal").fetchall()]
    for table in sorted(tables):
        rows = conn.execute(f'DESCRIBE "{table}"').fetchall()
        overview[table] = [(r[0], r[1]) for r in rows]
    return overview

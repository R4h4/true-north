"""Read the three sources of truth into plain dicts the compiler + access index consume.

- vocabulary: concepts + constraints (authored, knowledge-graph/vocabulary/)
- semantic:   metrics + dimensions (Agent A, source/semantic/)
- policy:     roles + users (governance/fixtures/users.yaml)
- schema.py:  physical tables (source/generator/schema.py)

Nothing here talks to Neo4j; the compiler turns these into nodes/edges and the
access index derives `_access` from the policy + semantic structure.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import yaml


def _load_yaml_dir(directory: Path) -> dict[str, dict]:
    docs: dict[str, dict] = {}
    directory = Path(directory)
    if not directory.is_dir():
        return docs
    for path in sorted(directory.glob("*.yml")):
        docs[path.stem] = yaml.safe_load(path.read_text())
    return docs


def load_vocabulary(vocab_dir: Path) -> dict:
    vocab_dir = Path(vocab_dir)
    return {
        "concepts": _load_yaml_dir(vocab_dir / "concepts"),
        "constraints": _load_yaml_dir(vocab_dir / "constraints"),
    }


def load_semantic(semantic_dir: Path) -> dict:
    semantic_dir = Path(semantic_dir)
    return {
        "metrics": _load_yaml_dir(semantic_dir / "metrics"),
        "dimensions": _load_yaml_dir(semantic_dir / "dimensions"),
    }


def load_policy(users_yaml: Path) -> dict:
    return yaml.safe_load(Path(users_yaml).read_text())


def load_schema(schema_py: Path):
    """Import source/generator/schema.py as a module (single source of truth for TABLES)."""
    import sys

    schema_py = Path(schema_py)
    spec = importlib.util.spec_from_file_location("_tn_schema", schema_py)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    # Register before exec so `from __future__ import annotations` dataclass field
    # resolution (which looks the module up in sys.modules) succeeds.
    sys.modules["_tn_schema"] = module
    spec.loader.exec_module(module)
    return module


# --- derived structure shared by compiler + access ------------------------

_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
# SQL-ish tokens that appear in measure exprs but are not column references.
_EXPR_KEYWORDS = {"and", "or", "not", "null", "case", "when", "then", "else", "end", "as", "distinct"}


def measure_tables(metric: dict) -> list[str]:
    """COMPUTED_FROM targets: the set of measure tables (join-only dim tables excluded).

    Order-preserving, deduplicated — deterministic across runs.
    """
    seen: list[str] = []
    for m in (metric.get("compute", {}).get("measures") or {}).values():
        t = m.get("table")
        if t and t not in seen:
            seen.append(t)
    return seen


def measure_columns(metric: dict) -> set[str]:
    """`table.column` references inside every measure's expr/filters, qualified by the
    measure's own table. Used for masked-column metric denial.
    """
    cols: set[str] = set()
    for m in (metric.get("compute", {}).get("measures") or {}).values():
        table = m.get("table")
        if not table:
            continue
        for token in _column_tokens(str(m.get("expr", ""))):
            cols.add(_qualify(token, table))
        for filt in m.get("filters") or []:
            column = filt.get("column")
            if column:
                cols.add(_qualify(column, table))
    return cols


def _column_tokens(expr: str) -> set[str]:
    tokens = set()
    for match in _IDENT.finditer(expr):
        tok = match.group(0)
        low = tok.lower()
        if low in _EXPR_KEYWORDS:
            continue
        if tok.replace(".", "").isdigit():
            continue
        tokens.add(tok)
    return tokens


def _qualify(column: str, default_table: str) -> str:
    """`store_id` -> `<table>.store_id`; `dim_x.col` passes through unchanged."""
    return column if "." in column else f"{default_table}.{column}"

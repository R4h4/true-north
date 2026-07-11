"""Per-role access derivation for KG `_access` annotations (CONTRACT §3).

Duplicates the governance derivation for the graph surface — kept in this one small
module and reconciled with `governance.policy` at integration (the e2e suite guards
drift). Rules follow governance/POLICY.md exactly:

- Table readable iff role's `tables` is `all` or lists it.
- Metric denied iff any measure table is unreadable (ACCESS_DENIED_TABLE, precedence)
  or any measure expr/filter column is masked (ACCESS_DENIED_METRIC, reason names column).
  Tokenized/transformed columns do NOT deny — they disclose.
- Dimension denied iff its `source` column is masked for the role.

`_access` is computed at serialization time from this index, never stored on nodes.
"""

from __future__ import annotations


def _measure_columns(metric) -> set[str]:
    """`table.column` refs inside every measure's expr/filters, qualified by the
    measure's own table. Used for masked-column metric denial."""
    import sqlglot
    import sqlglot.expressions as exp

    cols: set[str] = set()
    for m in metric.measures:
        if m.expr:
            try:
                tree = sqlglot.parse_one(m.expr, dialect="duckdb")
                for c in tree.find_all(exp.Column):
                    cols.add(c.name if "." in str(c) else f"{m.table}.{c.name}")
            except Exception:
                pass
        for filt in m.filters:
            column = filt.get("column") if isinstance(filt, dict) else None
            if column:
                cols.add(column if "." in column else f"{m.table}.{column}")
    return cols


class AccessIndex:
    """Answers readable/reason for Table, Metric, Dimension keys per role.

    Built once per compile from policy + semantic; the serializer holds one and
    calls it with the calling role.
    """

    def __init__(self, policy: dict, semantic) -> None:
        self._roles = policy.get("roles", {})
        self._metrics = semantic.metrics
        self._dimensions = semantic.dimensions

    # --- role helpers -----------------------------------------------------

    def roles(self) -> list[str]:
        return list(self._roles.keys())

    def _role(self, role: str) -> dict:
        r = self._roles.get(role)
        if r is None:
            raise KeyError(f"unknown role: {role}")
        return r

    def _readable_tables(self, role: str) -> str | set[str]:
        tables = self._role(role).get("tables", "all")
        return "all" if tables == "all" else set(tables)

    def _masked_columns(self, role: str) -> set[str]:
        return set(self._role(role).get("masked_columns") or [])

    # --- access answers ---------------------------------------------------

    def table_access(self, table_key: str, role: str) -> dict:
        readable = self._readable_tables(role)
        if readable == "all" or table_key in readable:
            return {"readable": True}
        return {
            "readable": False,
            "reason": f"{table_key} is not readable for role {role}",
        }

    def metric_access(self, metric_key: str, role: str) -> dict:
        metric = self._metrics.get(metric_key)
        if metric is None:
            # Unknown metric key: treat as readable=false with a plain reason rather
            # than crash; the compiler guarantees only real metric nodes reach here.
            return {"readable": False, "reason": f"metric {metric_key} is not defined"}

        # Table-read denial takes precedence over masked-column denial.
        readable = self._readable_tables(role)
        if readable != "all":
            for table in metric.tables:
                if table not in readable:
                    return {
                        "readable": False,
                        "reason": f"uses table {table}, not readable for role {role}",
                    }

        masked = self._masked_columns(role)
        if masked:
            for column in sorted(_measure_columns(metric)):
                if column in masked:
                    # reason names the bare column, matching the goldens
                    # ("uses masked column cost_amount").
                    bare = column.split(".", 1)[1]
                    return {"readable": False, "reason": f"uses masked column {bare}"}
        return {"readable": True}

    def dimension_access(self, dimension_key: str, role: str) -> dict:
        dim = self._dimensions.get(dimension_key)
        if dim is None:
            return {"readable": False, "reason": f"dimension {dimension_key} is not defined"}
        source = dim.source
        if source and source in self._masked_columns(role):
            bare = source.split(".", 1)[1]
            return {"readable": False, "reason": f"uses masked column {bare}"}
        return {"readable": True}

    # --- positive image, for CAN_READ / CAN_COMPUTE edges -----------------

    def can_read_tables(self, role: str, all_tables: list[str]) -> list[str]:
        return [t for t in all_tables if self.table_access(t, role)["readable"]]

    def can_compute_metrics(self, role: str) -> list[str]:
        return [m for m in self._metrics if self.metric_access(m, role)["readable"]]

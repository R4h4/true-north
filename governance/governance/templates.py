"""Named SQL builders for complex / window metrics.

Measure-mode compilation (governance.compiler) handles metrics that are plain
single-table aggregates combined arithmetically. Window and cross-grain metrics
— the two retention ratios, same-store growth, conversion, inventory days — need
per-entity or snapshot-aware logic that the measure model can't express, so each
gets a hand-built query here, keyed by `compute.template`.

Every builder returns a CompiledQuery (same shape the measure path returns) and
still honours governance: row-filter predicates are injected where the metric
touches a filtered table, time bounds bind to the metric's time column, and
group-by is limited to dimensions native to the metric's primary fact table
(the demo's fixtured complex queries only group by `channel`, which is native to
fact_sales_lines / fact_traffic).

SQL is rendered through sqlglot with the fixed duckdb dialect so it stays
byte-deterministic (ADR 0006).
"""

from __future__ import annotations

import sqlglot

_DIALECT = "duckdb"


def compile_template(
    name, metric, semantic, access, persona, *,
    group_dims, grain, filters, start, end, limit,
):
    from governance.compiler import CompiledColumn, CompiledQuery, CompileError, _dim_metric_type_unit

    builder = _BUILDERS.get(name)
    if builder is None:
        raise CompileError("INTERNAL", f"no template builder for '{name}'", {"template": name})

    group_cols = [d.key for d in group_dims]
    for d in group_dims:
        # complex builders only support fact-native group columns
        if d.key not in _NATIVE_GROUP_COLS.get(name, set()):
            raise CompileError(
                "INVALID_DIMENSION",
                f"metric '{metric.key}' cannot group by '{d.key}'",
                {"metric_key": metric.key, "valid_dimensions": sorted(_NATIVE_GROUP_COLS.get(name, []))},
            )

    row_predicates = _row_predicates(access, persona, _PRIMARY_TABLE[name])
    value_predicates = _value_predicates(semantic, filters)
    time_predicates = _time_predicates(_TIME_COL[name], start, end)

    raw_sql = builder(
        group_cols=group_cols,
        where=_and_clause(row_predicates + value_predicates + time_predicates),
        limit=limit,
    )
    sql = sqlglot.parse_one(raw_sql, dialect=_DIALECT).sql(dialect=_DIALECT, pretty=False, normalize=True)

    mtype, munit = _dim_metric_type_unit(metric)
    columns = []
    for d in group_dims:
        columns.append(CompiledColumn(name=d.key, type="categorical", unit=None))
    columns.append(CompiledColumn(name=metric.key, type=mtype, unit=munit))

    return CompiledQuery(
        sql=sql,
        columns=columns,
        tables=metric.tables,
        group_keys=group_cols,
        metric=metric,
        limit=limit,
    )


# --- per-template metadata --------------------------------------------------

_PRIMARY_TABLE = {
    "repeat_purchase_rate_90d": "fact_sales_lines",
    "member_active_rate_30d": "fact_sales_lines",
    "same_store_sales_growth": "fact_sales_lines",
    "conversion_rate": "fact_traffic",
    "inventory_days": "fact_inventory",
}
_TIME_COL = {
    "repeat_purchase_rate_90d": "ts",
    "member_active_rate_30d": "ts",
    "same_store_sales_growth": "ts",
    "conversion_rate": "date",
    "inventory_days": "snapshot_date",
}
_NATIVE_GROUP_COLS = {
    "repeat_purchase_rate_90d": {"channel"},
    "member_active_rate_30d": {"channel"},
    "same_store_sales_growth": {"channel"},
    "conversion_rate": set(),
    "inventory_days": set(),
}


# --- predicate helpers ------------------------------------------------------


def _row_predicates(access, persona, table):
    return [rf.predicate for rf in access.row_filters(persona) if table in rf.apply_to]


def _value_predicates(semantic, filters):
    out = []
    for fc in filters:
        dim = semantic.dimension(fc.dimension)
        col = dim.column  # native column on the primary table (validated upstream)
        if fc.operator == "=":
            out.append(f"{col} = '{fc.values[0]}'")
        else:
            vals = ", ".join(f"'{v}'" for v in fc.values)
            out.append(f"{col} IN ({vals})")
    return out


def _time_predicates(time_col, start, end):
    out = []
    if start is not None:
        out.append(f"CAST({time_col} AS DATE) >= '{start}'")
    if end is not None:
        out.append(f"CAST({time_col} AS DATE) <= '{end}'")
    return out


def _and_clause(predicates):
    return " AND ".join(f"({p})" for p in predicates) if predicates else ""


def _select_prefix(group_cols):
    return (", ".join(group_cols) + ", ") if group_cols else ""


def _group_order(group_cols):
    if not group_cols:
        return ""
    cols = ", ".join(group_cols)
    return f"GROUP BY {cols} ORDER BY {cols}"


# --- builders ---------------------------------------------------------------


def _repeat_purchase_rate_90d(group_cols, where, limit):
    gsel = _select_prefix(group_cols)
    gjoin = _group_order(group_cols)
    where_clause = f"WHERE customer_id IS NOT NULL AND ({where})" if where else "WHERE customer_id IS NOT NULL"
    # per customer: first purchase ts + its channel; and whether a 2nd purchase
    # falls within 90 days of the first.
    return f"""
    WITH ranked AS (
      SELECT customer_id, channel, ts,
             ROW_NUMBER() OVER (PARTITION BY customer_id ORDER BY ts) AS rn,
             MIN(ts) OVER (PARTITION BY customer_id) AS first_ts
      FROM fact_sales_lines
      {where_clause}
    ),
    per_customer AS (
      SELECT customer_id,
             MAX(CASE WHEN rn = 1 THEN channel END) AS channel,
             MIN(CASE WHEN rn >= 2 THEN ts END) AS second_ts,
             MIN(first_ts) AS first_ts
      FROM ranked
      GROUP BY customer_id
    )
    SELECT {gsel}
           CAST(COUNT(*) FILTER (
             WHERE second_ts IS NOT NULL
               AND date_diff('day', CAST(first_ts AS DATE), CAST(second_ts AS DATE)) <= 90
           ) AS DOUBLE) / NULLIF(COUNT(*), 0) AS repeat_purchase_rate_90d
    FROM per_customer
    {gjoin}
    LIMIT {limit}
    """


def _member_active_rate_30d(group_cols, where, limit):
    gsel = _select_prefix(group_cols)
    gjoin = _group_order(group_cols)
    active_where = f"WHERE customer_id IS NOT NULL AND ({where})" if where else "WHERE customer_id IS NOT NULL"
    # active = distinct members purchasing in the 30 days ending at the latest ts;
    # denominator = all loyalty members (dim_customer).
    return f"""
    WITH bound AS (SELECT MAX(ts) AS max_ts FROM fact_sales_lines),
    active AS (
      SELECT DISTINCT s.customer_id, s.channel
      FROM fact_sales_lines s, bound
      {active_where.replace('customer_id', 's.customer_id')}
        AND s.ts >= (SELECT max_ts FROM bound) - INTERVAL 30 DAY
    ),
    members AS (SELECT COUNT(*) AS total FROM dim_customer)
    SELECT {gsel}
           CAST(COUNT(DISTINCT active.customer_id) AS DOUBLE)
             / NULLIF((SELECT total FROM members), 0) AS member_active_rate_30d
    FROM active
    {gjoin}
    LIMIT {limit}
    """


def _same_store_sales_growth(group_cols, where, limit):
    gsel = _select_prefix(group_cols)
    gjoin = _group_order(group_cols)
    where_clause = f"WHERE ({where})" if where else ""
    # like-for-like: only stores open >=13 months before the window and not closed
    # during it. Compares the latest 12 months vs the prior 12 months of net_amount.
    return f"""
    WITH bounds AS (SELECT MAX(CAST(ts AS DATE)) AS max_d FROM fact_sales_lines),
    eligible AS (
      SELECT store_id FROM dim_store, bounds
      WHERE opened_date <= (SELECT max_d FROM bounds) - INTERVAL 25 MONTH
        AND (closed_date IS NULL OR closed_date > (SELECT max_d FROM bounds))
    ),
    windows AS (
      SELECT s.store_id, s.channel,
             SUM(CASE WHEN CAST(s.ts AS DATE) > (SELECT max_d FROM bounds) - INTERVAL 12 MONTH
                      THEN s.net_amount ELSE 0 END) AS cur,
             SUM(CASE WHEN CAST(s.ts AS DATE) <= (SELECT max_d FROM bounds) - INTERVAL 12 MONTH
                      AND CAST(s.ts AS DATE) > (SELECT max_d FROM bounds) - INTERVAL 24 MONTH
                      THEN s.net_amount ELSE 0 END) AS prior
      FROM fact_sales_lines s
      JOIN eligible e ON s.store_id = e.store_id
      {where_clause.replace('channel', 's.channel')}
      GROUP BY s.store_id, s.channel
    )
    SELECT {gsel}
           (SUM(cur) - SUM(prior)) / NULLIF(SUM(prior), 0) AS same_store_sales_growth
    FROM windows
    {gjoin}
    LIMIT {limit}
    """


def _conversion_rate(group_cols, where, limit):
    gsel = _select_prefix(group_cols)
    gjoin = _group_order(group_cols)
    where_clause = f"WHERE ({where})" if where else ""
    return f"""
    SELECT {gsel}
           CAST(SUM(transaction_count) AS DOUBLE) / NULLIF(SUM(footfall), 0) AS conversion_rate
    FROM fact_traffic
    {where_clause}
    {gjoin}
    LIMIT {limit}
    """


def _inventory_days(group_cols, where, limit):
    gsel = _select_prefix(group_cols)
    where_clause = f"WHERE ({where})" if where else ""
    # avg on-hand per store x sku across weekly snapshots (never summed), divided by
    # average weekly units sold, x7. Grouping is not exposed for the demo.
    return f"""
    WITH inv AS (
      SELECT AVG(on_hand_qty) AS avg_on_hand
      FROM fact_inventory
      {where_clause}
    ),
    sold AS (
      SELECT SUM(qty) AS units,
             COUNT(DISTINCT date_trunc('week', ts)) AS weeks
      FROM fact_sales_lines
    )
    SELECT 7.0 * inv.avg_on_hand
             / NULLIF(sold.units / NULLIF(sold.weeks, 0), 0) AS inventory_days
    FROM inv, sold
    LIMIT {limit}
    """


_BUILDERS = {
    "repeat_purchase_rate_90d": _repeat_purchase_rate_90d,
    "member_active_rate_30d": _member_active_rate_30d,
    "same_store_sales_growth": _same_store_sales_growth,
    "conversion_rate": _conversion_rate,
    "inventory_days": _inventory_days,
}

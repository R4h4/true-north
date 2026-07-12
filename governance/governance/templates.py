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

    # templates listed in _GRAIN_COL group by their (truncated) time column when
    # --grain is given; the rest keep ignoring grain, byte-identical to before
    grain_col = _GRAIN_COL.get(name) if grain is not None else None

    row_predicates = _row_predicates(access, persona, _PRIMARY_TABLE[name])
    value_predicates = _value_predicates(semantic, filters, _FILTER_COLS.get(name))
    time_predicates = _time_predicates(_TIME_COL[name], start, end)

    raw_sql = builder(
        group_cols=group_cols,
        where=_and_clause(row_predicates + value_predicates + time_predicates),
        limit=limit,
        grain=grain if grain_col else None,
    )
    sql = sqlglot.parse_one(raw_sql, dialect=_DIALECT).sql(dialect=_DIALECT, pretty=False, normalize=True)

    mtype, munit = _dim_metric_type_unit(metric)
    columns = []
    if grain_col:
        columns.append(CompiledColumn(name=grain_col, type="time", unit=None))
    for d in group_dims:
        columns.append(CompiledColumn(name=d.key, type="categorical", unit=None))
    columns.append(CompiledColumn(name=metric.key, type=mtype, unit=munit))

    return CompiledQuery(
        sql=sql,
        columns=columns,
        tables=metric.tables,
        group_keys=([grain_col] if grain_col else []) + group_cols,
        metric=metric,
        limit=limit,
    )


def available_templates() -> frozenset[str]:
    """Template names fully wired for dispatch: a builder plus every metadata
    entry compile_template dereferences. The semantic validator checks each
    metric's ``compute.template`` against this — a declared-but-unbuilt
    template otherwise only fails at query time, as INTERNAL (demo, 2026-07-12)."""
    return (
        frozenset(_BUILDERS)
        & frozenset(_PRIMARY_TABLE)
        & frozenset(_TIME_COL)
        & frozenset(_NATIVE_GROUP_COLS)
    )


# --- per-template metadata --------------------------------------------------

_PRIMARY_TABLE = {
    "repeat_purchase_rate_90d": "fact_sales_lines",
    "member_active_rate_30d": "fact_sales_lines",
    "same_store_sales_growth": "fact_sales_lines",
    "conversion_rate": "fact_traffic",
    "inventory_days": "fact_inventory",
    "fpd_rate": "fact_disbursements",
}
_TIME_COL = {
    "repeat_purchase_rate_90d": "ts",
    "member_active_rate_30d": "ts",
    "same_store_sales_growth": "ts",
    "conversion_rate": "date",
    "inventory_days": "snapshot_date",
    # vintage metric: --start/--end bound the DISBURSEMENT month, never the
    # observation snapshot (see the fpd_rate metric caveat)
    "fpd_rate": "disbursed_date",
}
_NATIVE_GROUP_COLS = {
    "repeat_purchase_rate_90d": {"channel"},
    "member_active_rate_30d": {"channel"},
    "same_store_sales_growth": {"channel"},
    "conversion_rate": set(),
    "inventory_days": set(),
    "fpd_rate": {"product", "channel"},
}
# dim key -> physical column on the primary fact, where it differs from the
# dimension's own source column (product/channel resolve via dims on shinhan)
_FPD_GROUP_COL = {"product": "product_key", "channel": "channel"}
_FILTER_COLS = {
    "fpd_rate": _FPD_GROUP_COL,
}
# templates that honour --grain, and the alias their time group column gets
_GRAIN_COL = {
    "fpd_rate": "vintage_month",
}


# --- predicate helpers ------------------------------------------------------


def _row_predicates(access, persona, table):
    return [rf.predicate for rf in access.row_filters(persona) if table in rf.apply_to]


def _value_predicates(semantic, filters, colmap=None):
    out = []
    for fc in filters:
        dim = semantic.dimension(fc.dimension)
        # native column on the primary table (validated upstream); a template's
        # _FILTER_COLS entry wins when the dim's source column isn't on the fact
        col = (colmap or {}).get(fc.dimension) or dim.column
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


def _repeat_purchase_rate_90d(group_cols, where, limit, grain=None):
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


def _member_active_rate_30d(group_cols, where, limit, grain=None):
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


def _same_store_sales_growth(group_cols, where, limit, grain=None):
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


def _conversion_rate(group_cols, where, limit, grain=None):
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


def _inventory_days(group_cols, where, limit, grain=None):
    where_clause = f"AND ({where})" if where else ""
    # Days of cover: total units on hand at the LATEST weekly snapshot, divided by
    # average DAILY units sold. Never sum on_hand across snapshot weeks (trap 5) —
    # we take one snapshot date. Inventory and sales are at the same network grain.
    return f"""
    WITH latest AS (SELECT MAX(snapshot_date) AS d FROM fact_inventory),
    inv AS (
      SELECT SUM(on_hand_qty) AS on_hand
      FROM fact_inventory, latest
      WHERE snapshot_date = latest.d {where_clause}
    ),
    sold AS (
      SELECT SUM(qty) AS units,
             GREATEST(date_diff('day', MIN(CAST(ts AS DATE)), MAX(CAST(ts AS DATE))), 1) AS days
      FROM fact_sales_lines
    )
    SELECT inv.on_hand / NULLIF(sold.units / NULLIF(sold.days, 0), 0) AS inventory_days
    FROM inv, sold
    LIMIT {limit}
    """


def _fpd_rate(group_cols, where, limit, grain=None):
    # Vintage metric (shinhan): share of a DISBURSEMENT-MONTH cohort whose
    # snapshot shows dpd >= 30 within 2 snapshot months of disbursement. The
    # cohort universe is fact_disbursements — where (row filters, product/
    # channel filters, --start/--end on disbursed_date) applies there, so a
    # loan excluded from the cohort can never leak in via the numerator join.
    sel_parts = []
    group_parts = []
    if grain is not None:
        sel_parts.append(f"DATE_TRUNC('{grain}', disbursed_date) AS vintage_month")
        group_parts.append("vintage_month")
    for key in group_cols:
        sel_parts.append(f"{_FPD_GROUP_COL[key]} AS {key}")
        group_parts.append(key)
    gsel = (", ".join(sel_parts) + ", ") if sel_parts else ""
    gjoin = _group_order(group_parts)
    where_clause = f"WHERE ({where})" if where else ""
    return f"""
    WITH fpd AS (
      SELECT DISTINCT s.loan_id
      FROM fact_loan_snapshots AS s
      JOIN fact_disbursements AS dd ON s.loan_id = dd.loan_id
      WHERE s.dpd >= 30
        AND DATE_DIFF('month', DATE_TRUNC('month', dd.disbursed_date),
                      DATE_TRUNC('month', s.snapshot_month)) BETWEEN 0 AND 2
    )
    SELECT {gsel}
           CAST(COUNT(fpd.loan_id) AS DOUBLE) / NULLIF(COUNT(*), 0) AS fpd_rate
    FROM fact_disbursements
    LEFT JOIN fpd ON fact_disbursements.loan_id = fpd.loan_id
    {where_clause}
    {gjoin}
    LIMIT {limit}
    """


_BUILDERS = {
    "repeat_purchase_rate_90d": _repeat_purchase_rate_90d,
    "member_active_rate_30d": _member_active_rate_30d,
    "same_store_sales_growth": _same_store_sales_growth,
    "conversion_rate": _conversion_rate,
    "inventory_days": _inventory_days,
    "fpd_rate": _fpd_rate,
}

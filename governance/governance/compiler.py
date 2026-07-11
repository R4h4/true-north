"""SQLGlot compiler: (metric, persona, query args) -> deterministic DuckDB SQL.

ADR 0006: the compiled query is built as a SQLGlot AST and rendered with a fixed
dialect (duckdb) and normalized formatting, so identical input -> byte-identical
SQL. The DSL is closed (validated keys + canonical values), never user SQL.

Measure-mode metrics (gmv_gross, net_revenue, gross_margin, basket_*_avg) are
assembled here. Complex/window metrics carry `compute.template` and are routed to
governance.templates. Governance (row filters, masking, tokenization, banding) is
injected at compile time from a RoleAccess.

The public entrypoint is `compile_query`, returning a CompiledQuery with the SQL
string, the projected columns (name/type/unit), the touched tables, and the
applied-permission disclosures.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import sqlglot
import sqlglot.expressions as exp

from governance.filters import FilterClause, parse_filter, validate_value
from governance.policy import Persona, RoleAccess
from semantic_layer import Dimension, Measure, Metric, SemanticLayer
from governance import templates as _templates
from governance import tokenization as _tok

# fixed render settings — determinism (ADR 0006)
_DIALECT = "duckdb"
_GRAIN_TRUNC = {
    "day": "day",
    "week": "week",
    "month": "month",
    "quarter": "quarter",
    "year": "year",
}


class CompileError(ValueError):
    def __init__(self, code: str, message: str, details: dict):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details


@dataclass
class CompiledColumn:
    name: str
    type: str
    unit: str | None


@dataclass
class CompiledQuery:
    sql: str
    columns: list[CompiledColumn]
    tables: list[str]                 # measure tables (COMPUTED_FROM order)
    group_keys: list[str]             # output column names of the group dims (time first)
    metric: Metric
    limit: int
    applied_permissions: list[dict] = field(default_factory=list)


def _q(name: str) -> exp.Column:
    return exp.column(name)


def _agg_expr(agg: str, inner: exp.Expression) -> exp.Expression:
    if agg == "sum":
        return exp.func("SUM", inner)
    if agg == "count":
        return exp.func("COUNT", inner)
    if agg == "avg":
        return exp.func("AVG", inner)
    if agg == "count_distinct":
        return exp.Count(this=exp.Distinct(expressions=[inner]))
    raise CompileError("INTERNAL", f"unknown agg '{agg}'", {"agg": agg})


def _dim_metric_type_unit(metric: Metric) -> tuple[str, str | None]:
    """The (type, unit) label for the metric's value column in result.columns.

    Illustrative under the golden matchers, but we make them truthful:
    VND -> money, ratio -> ratio, count -> count.
    """
    if metric.unit == "VND":
        return ("money", "VND")
    if metric.unit == "ratio":
        return ("ratio", "ratio")
    if metric.unit == "count":
        return ("count", "count")
    return (metric.type, metric.unit)


def _resolve_dim(metric: Metric, semantic: SemanticLayer, dim_key: str) -> Dimension:
    if dim_key not in metric.dimensions:
        raise CompileError(
            "INVALID_DIMENSION",
            f"'{dim_key}' is not a governed dimension of metric '{metric.key}'",
            {"metric_key": metric.key, "valid_dimensions": sorted(metric.dimensions)},
        )
    dim = semantic.dimension(dim_key)
    if dim is None:
        raise CompileError(
            "INTERNAL",
            f"dimension '{dim_key}' missing from semantic layer",
            {"dimension": dim_key},
        )
    return dim


def _join_for_table(measure: Measure, target_table: str) -> dict | None:
    for j in measure.joins:
        if j.get("table") == target_table:
            return j
    return None


def _resolve_join_order(measure: Measure, needed: set[str]) -> list[dict]:
    """Declared-order list of joins to apply: every needed table plus any table a
    needed join's `left_on` references (transitively). A join whose left side is
    `<table>.<col>` requires `<table>` to be present first."""
    want = set(needed)
    # transitively add prerequisites referenced by a needed join's left_on
    changed = True
    while changed:
        changed = False
        for jt in list(want):
            j = _join_for_table(measure, jt)
            if j is None:
                raise CompileError(
                    "INTERNAL",
                    f"measure '{measure.name}' has no join to '{jt}'",
                    {"table": jt},
                )
            left_on = str(j.get("left_on", ""))
            if "." in left_on:
                prereq = left_on.split(".", 1)[0]
                if prereq != measure.table and prereq not in want:
                    want.add(prereq)
                    changed = True
    # emit in declared order
    return [j for j in measure.joins if j.get("table") in want]


def _column_ref(table: str, column: str) -> exp.Column:
    return exp.column(column, table=table)


def _dim_projection(
    measure: Measure, dim: Dimension, access: RoleAccess, alias: str
) -> tuple[exp.Expression, str, str | None]:
    """Return (projection expr aliased, output col type, unit) for a group dim on
    this measure's query. Applies tokenization/banding transforms if the backing
    column carries one for the role. Masked columns must have been rejected before
    this point.
    """
    src_table, src_col = dim.table, dim.column
    base = _column_ref(src_table, src_col)
    qualified = dim.source
    if access.is_tokenized(qualified):
        # tokenization is applied post-fetch in Python (HMAC), but for group-by we
        # must group on a stable expression; DuckDB has no HMAC builtin, so we
        # group on the raw column and tokenize the value on the way out. The raw
        # value never leaves the process — see engine post-processing.
        return (base.as_(alias), "categorical", None)
    if access.transform_of(qualified):
        return (base.as_(alias), "categorical", None)
    return (base.as_(alias), _dim_type(dim), None)


def _dim_type(dim: Dimension) -> str:
    return "categorical" if dim.type == "categorical" else dim.type


def _time_bucket(col: exp.Column, grain: str) -> exp.Expression:
    trunc = _GRAIN_TRUNC[grain]
    bucket = exp.func("DATE_TRUNC", exp.Literal.string(trunc), col)
    # buckets are calendar dates, not timestamps (§2 DATE serialization)
    return exp.Cast(this=bucket, to=exp.DataType.build("DATE"))


def _build_measure_query(
    metric: Metric,
    measure: Measure,
    semantic: SemanticLayer,
    access: RoleAccess,
    persona: Persona,
    group_dims: list[Dimension],
    grain: str | None,
    filters: list[FilterClause],
    start: str | None,
    end: str | None,
) -> tuple[exp.Select, list[str]]:
    """Build the per-measure aggregate subquery and return (select, group_key_aliases)."""
    select = exp.Select()
    from_table = measure.table
    select = select.from_(from_table)

    needed_join_tables: set[str] = set()
    group_key_aliases: list[str] = []
    projections: list[exp.Expression] = []

    # time bucket first when grain is set
    if grain is not None and measure.time_column is not None:
        tcol = _column_ref(measure.table, measure.time_column)
        projections.append(_time_bucket(tcol, grain).as_(metric.time_dimension))
        group_key_aliases.append(metric.time_dimension)

    # group dimensions
    for dim in group_dims:
        if dim.table and dim.table != measure.table:
            needed_join_tables.add(dim.table)
        proj, _, _ = _dim_projection(measure, dim, access, dim.key)
        projections.append(proj)
        group_key_aliases.append(dim.key)

    # the measure aggregate
    inner = sqlglot.parse_one(measure.expr, dialect=_DIALECT)
    inner = _qualify_bare(inner, measure.table)
    projections.append(_agg_expr(measure.agg, inner).as_(measure.name))

    select = select.select(*projections, append=False)

    # value filters may reference dims not in group-by; they still need joins
    for fc in filters:
        dim = semantic.dimension(fc.dimension)
        if dim and dim.table and dim.table != measure.table:
            needed_join_tables.add(dim.table)

    # joins needed for grouped/filtered dims. Row-filter predicates may need a
    # join too: a returns measure scoped to a region reaches store via its join to
    # fact_sales_lines, so if the predicate's apply_to table is reachable by a
    # declared join we pull it in.
    for rf in access.row_filters(persona):
        for at in rf.apply_to:
            if at != measure.table and _join_for_table(measure, at) is not None:
                needed_join_tables.add(at)

    # resolve joins in DECLARED order, pulling in any prerequisite table a needed
    # join's left side references (e.g. dim_store ON fact_sales_lines.store_id
    # requires fact_sales_lines to be joined first).
    ordered = _resolve_join_order(measure, needed_join_tables)
    present_tables = {measure.table}
    for j in ordered:
        select = _apply_join(select, measure.table, j)
        present_tables.add(j["table"])

    # WHERE: structured measure filters + value filters + row filters + time
    conditions: list[exp.Expression] = []
    for sf in measure.filters:
        conditions.append(_structured_filter(measure.table, sf))
    for fc in filters:
        conditions.append(_value_filter(semantic, fc))
    for rf in access.row_filters(persona):
        # apply the predicate to whichever apply_to table is present in this
        # measure query (base or joined), qualifying its bare columns to it.
        target = next((at for at in rf.apply_to if at in present_tables), None)
        if target is not None:
            conditions.append(_qualify_toplevel(sqlglot.parse_one(rf.predicate, dialect=_DIALECT), target))
    if measure.time_column is not None:
        tcol = _column_ref(measure.table, measure.time_column)
        if start is not None:
            conditions.append(exp.GTE(this=_date_cast(tcol), expression=exp.Literal.string(start)))
        if end is not None:
            conditions.append(exp.LTE(this=_date_cast(tcol), expression=exp.Literal.string(end)))
    if conditions:
        select = select.where(*conditions)

    if group_key_aliases:
        select = select.group_by(*[exp.column(a) for a in _group_by_positions(group_key_aliases)])

    return select, group_key_aliases


def _group_by_positions(aliases: list[str]) -> list[str]:
    # group by the projected aliases (DuckDB allows grouping by output alias)
    return aliases


def _date_cast(col: exp.Column) -> exp.Expression:
    return exp.Cast(this=col, to=exp.DataType.build("DATE"))


def _qualify_bare(tree: exp.Expression, table: str) -> exp.Expression:
    for c in tree.find_all(exp.Column):
        if c.table == "":
            c.set("table", exp.to_identifier(table))
    return tree


def _qualify_toplevel(tree: exp.Expression, table: str) -> exp.Expression:
    """Qualify bare columns to `table`, but leave columns inside a nested
    subquery (e.g. `store_id IN (SELECT store_id FROM dim_store ...)`) alone —
    those resolve against their own scope."""
    for c in tree.find_all(exp.Column):
        if c.table:
            continue
        # columns inside a nested SELECT resolve against their own scope
        if c.find_ancestor(exp.Select) is not None:
            continue
        c.set("table", exp.to_identifier(table))
    return tree


def _apply_join(select: exp.Select, left_table: str, j: dict) -> exp.Select:
    jt = j["table"]
    left_on = str(j["left_on"])
    right_on = str(j["right_on"])
    if "." in left_on:
        lt, lc = left_on.split(".", 1)
    else:
        lt, lc = left_table, left_on
    on = exp.EQ(this=_column_ref(lt, lc), expression=_column_ref(jt, right_on))

    distinct_key = j.get("distinct_key")
    if distinct_key:
        # join to a grain-collapsed subquery aliased as the physical table name,
        # so downstream `<table>.<carry>` references still resolve. Prevents a
        # one-to-many join (e.g. returns -> sales lines) from fanning the measure.
        carry = j.get("carry") or []
        sub = exp.Select().from_(jt)
        projections = [exp.column(distinct_key, table=jt).as_(distinct_key)]
        for c in carry:
            projections.append(exp.func("ANY_VALUE", exp.column(c, table=jt)).as_(c))
        sub = sub.select(*projections, append=False).group_by(exp.column(distinct_key, table=jt))
        joined = sub.subquery(alias=jt)
        return select.join(joined, on=on, join_type="LEFT")

    return select.join(jt, on=on, join_type="LEFT")


def _structured_filter(table: str, sf: dict) -> exp.Expression:
    col = _column_ref(table, sf["column"])
    op = sf.get("operator", "=")
    val = sf["value"]
    lit = exp.Literal.string(val) if isinstance(val, str) else exp.Literal.number(val)
    if op == "=":
        return exp.EQ(this=col, expression=lit)
    if op == "!=":
        return exp.NEQ(this=col, expression=lit)
    raise CompileError("INTERNAL", f"unsupported structured filter op '{op}'", {"op": op})


def _value_filter(semantic: SemanticLayer, fc: FilterClause) -> exp.Expression:
    dim = semantic.dimension(fc.dimension)
    col = _column_ref(dim.table, dim.column)
    lits = [exp.Literal.string(v) for v in fc.values]
    if fc.operator == "=":
        return exp.EQ(this=col, expression=lits[0])
    return exp.In(this=col, expressions=lits)


def compile_query(
    metric: Metric,
    semantic: SemanticLayer,
    access: RoleAccess,
    persona: Persona,
    *,
    group_by: list[str] | None = None,
    grain: str | None = None,
    filter_strs: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int = 1000,
) -> CompiledQuery:
    group_by = group_by or []
    filter_strs = filter_strs or []

    if grain is not None and grain not in _GRAIN_TRUNC:
        raise CompileError(
            "INVALID_QUERY", f"unknown grain '{grain}'", {"grain": grain}
        )

    # resolve group-by dims (validates governed + not masked/denied)
    group_dims: list[Dimension] = []
    for gk in group_by:
        dim = _resolve_dim(metric, semantic, gk)
        denial = access.dimension_denial(gk)
        if denial is not None:
            raise CompileError(denial.code, f"dimension '{gk}' is not accessible", {
                "dimension": gk, "reason": denial.reason,
            })
        group_dims.append(dim)

    # parse + validate filters (canonical values, and denied dims)
    filters: list[FilterClause] = []
    for raw in filter_strs:
        fdim, op, values = parse_filter(raw)
        dim = semantic.dimension(fdim)
        if dim is None or fdim not in metric.dimensions:
            raise CompileError(
                "INVALID_DIMENSION",
                f"'{fdim}' is not a governed dimension of metric '{metric.key}'",
                {"metric_key": metric.key, "valid_dimensions": sorted(metric.dimensions)},
            )
        denial = access.dimension_denial(fdim)
        if denial is not None:
            raise CompileError(denial.code, f"dimension '{fdim}' is not accessible", {
                "dimension": fdim, "reason": denial.reason,
            })
        canonical = list(dim.canonical_values)
        for v in values:
            validate_value(fdim, v, canonical)
        filters.append(FilterClause(dimension=fdim, values=values, operator=op))

    # complex metrics route to a named template builder
    if metric.template is not None:
        return _templates.compile_template(
            metric.template, metric, semantic, access, persona,
            group_dims=group_dims, grain=grain, filters=filters,
            start=start, end=end, limit=limit,
        )

    return _compile_measure_mode(
        metric, semantic, access, persona,
        group_dims=group_dims, grain=grain, filters=filters,
        start=start, end=end, limit=limit,
    )


def _compile_measure_mode(
    metric, semantic, access, persona, *,
    group_dims, grain, filters, start, end, limit,
) -> CompiledQuery:
    measure_selects: list[tuple[Measure, exp.Select, list[str]]] = []
    group_key_aliases: list[str] = []
    for measure in metric.measures:
        sel, keys = _build_measure_query(
            metric, measure, semantic, access, persona,
            group_dims, grain, filters, start, end,
        )
        measure_selects.append((measure, sel, keys))
        group_key_aliases = keys  # identical across measures

    outer = _combine_measures(metric, measure_selects, group_key_aliases)

    # ORDER BY grouped columns ascending (time first — already first in aliases)
    if group_key_aliases:
        outer = outer.order_by(*[exp.column(a).asc() for a in group_key_aliases])
    outer = outer.limit(limit)

    sql = outer.sql(dialect=_DIALECT, pretty=False, normalize=True)

    columns = _output_columns(metric, group_dims, group_key_aliases, grain)
    return CompiledQuery(
        sql=sql,
        columns=columns,
        tables=metric.tables,
        group_keys=group_key_aliases,
        metric=metric,
        limit=limit,
    )


def _combine_measures(metric, measure_selects, group_key_aliases) -> exp.Select:
    """Wrap each measure subquery as a CTE, join on the group keys, project the
    compute.expr as the metric column."""
    if len(measure_selects) == 1 and not _needs_cte(measure_selects[0][0], metric):
        # simple single-measure metric: project the compute.expr directly
        measure, sel, keys = measure_selects[0]
        outer = exp.Select().from_(sel.subquery(alias="m0"))
        proj = [exp.column(k, table="m0").as_(k) for k in keys]
        value_expr = _compute_expr_over({measure.name: exp.column(metric.measures[0].name, table="m0")}, metric.expr)
        proj.append(value_expr.as_(metric.key))
        return outer.select(*proj, append=False)

    # multi-measure: CTEs joined on group keys
    ctes = []
    first = measure_selects[0]
    cte_aliases = []
    for i, (measure, sel, keys) in enumerate(measure_selects):
        alias = f"m{i}"
        cte_aliases.append(alias)
        ctes.append((alias, sel))

    base_alias = cte_aliases[0]
    outer = exp.Select().from_(base_alias)
    # from first CTE, full outer join the rest on group keys
    for i in range(1, len(cte_aliases)):
        a = cte_aliases[i]
        if group_key_aliases:
            on = _join_on_keys(base_alias, a, group_key_aliases)
        else:
            on = exp.condition("TRUE")
        outer = outer.join(a, on=on, join_type="FULL OUTER")

    # projections: coalesce group keys across CTEs; then compute.expr
    proj = []
    for k in group_key_aliases:
        coalesced = exp.func("COALESCE", *[exp.column(k, table=a) for a in cte_aliases])
        proj.append(coalesced.as_(k))
    measure_cols = {
        m.name: exp.func("COALESCE", exp.column(m.name, table=cte_aliases[i]), exp.Literal.number(0))
        for i, (m, _, _) in enumerate(measure_selects)
    }
    value_expr = _compute_expr_over(measure_cols, metric.expr)
    proj.append(value_expr.as_(metric.key))
    outer = outer.select(*proj, append=False)

    for a, sel in ctes:
        outer = outer.with_(a, as_=sel)
    return outer


def _needs_cte(measure, metric) -> bool:
    return len(metric.measures) > 1


def _join_on_keys(left_alias, right_alias, keys) -> exp.Expression:
    conds = [
        exp.EQ(this=exp.column(k, table=left_alias), expression=exp.column(k, table=right_alias))
        for k in keys
    ]
    out = conds[0]
    for c in conds[1:]:
        out = exp.And(this=out, expression=c)
    return out


def _compute_expr_over(measure_cols: dict[str, exp.Expression], expr: str) -> exp.Expression:
    """Parse compute.expr and substitute each measure name with its column expr,
    protecting division against zero denominators via NULLIF."""
    tree = sqlglot.parse_one(expr, dialect=_DIALECT)
    # replace division a / b with a / NULLIF(b, 0)
    for div in list(tree.find_all(exp.Div)):
        denom = div.expression
        div.set("expression", exp.func("NULLIF", denom.copy(), exp.Literal.number(0)))
    # substitute columns
    for col in list(tree.find_all(exp.Column)):
        name = col.name
        if name in measure_cols:
            col.replace(measure_cols[name].copy())
    return tree


def _output_columns(metric, group_dims, group_key_aliases, grain) -> list[CompiledColumn]:
    cols: list[CompiledColumn] = []
    idx = 0
    if grain is not None:
        cols.append(CompiledColumn(name=metric.time_dimension, type="time", unit=None))
        idx = 1
    for dim in group_dims:
        cols.append(CompiledColumn(name=dim.key, type=_dim_type(dim), unit=None))
    mtype, munit = _dim_metric_type_unit(metric)
    cols.append(CompiledColumn(name=metric.key, type=mtype, unit=munit))
    return cols

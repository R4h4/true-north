"""Real warehouse-surface command implementations for the `tn` CLI.

Replaces the replay path for: whoami, metrics list/describe, dimensions
list/describe, query. The KG commands stay on the replay stub (wired to Agent B's
graph later by the coordinator).

Each function returns a complete envelope dict (CONTRACT §2). Auth is resolved
first; an unknown token is AUTH_INVALID_TOKEN. Governance (denials, row filters,
masking, tokenization, banding, disclosure) is derived from policy.py; SQL is
built by compiler.py and executed read-only via the source query engine.
"""

from __future__ import annotations

from pathlib import Path

from governance import constraints as _constraints
from governance import envelope as _env
from governance import tokenization as _tok
from governance.compiler import CompileError, CompiledQuery, compile_query
from governance.filters import FilterError
from governance.policy import Policy, RoleAccess, load_policy
from semantic_layer import Metric, SemanticLayer, load_semantic, schema_module

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "source" / "data"


# --- shared plumbing --------------------------------------------------------


def _services() -> tuple[SemanticLayer, Policy]:
    sem = load_semantic()
    pol = load_policy(semantic=sem)
    return sem, pol


def _auth(pol: Policy, token: str):
    persona = pol.resolve_token(token)
    if persona is None:
        return None, _env.error_envelope(None, "AUTH_INVALID_TOKEN", "unknown token", None)
    return persona, None


def _metric_catalog_type(metric: Metric) -> str:
    return metric.type


# --- whoami -----------------------------------------------------------------


def whoami(token: str) -> dict:
    sem, pol = _services()
    persona, err = _auth(pol, token)
    if err:
        return err
    access = pol.access_for(persona.role)
    result = {
        "user": persona.public,
        "readable_tables": access.readable_tables,
        "denied_metrics": access.denied_metrics(),
        "permissions": access.permission_objects(persona),
    }
    return _env.ok_envelope(persona.public_short(), result, {}, [])


# --- metrics ----------------------------------------------------------------


def metrics_list(token: str) -> dict:
    sem, pol = _services()
    persona, err = _auth(pol, token)
    if err:
        return err
    access = pol.access_for(persona.role)
    metrics = []
    for key, m in sem.metrics.items():
        reason = access.metric_reason_for_catalog(key)
        metrics.append({
            "key": m.key,
            "name": m.name,
            "short_description": m.short_description,
            "type": m.type,
            "unit": m.unit,
            "access": {"allowed": reason is None, "reason": reason},
        })
    return _env.ok_envelope(persona.public_short(), {"metrics": metrics}, {}, [])


def metrics_describe(key: str, token: str) -> dict:
    sem, pol = _services()
    persona, err = _auth(pol, token)
    if err:
        return err
    access = pol.access_for(persona.role)
    metric = sem.metric(key)
    if metric is None:
        return _metric_not_found(sem, persona, key)
    reason = access.metric_reason_for_catalog(key)
    dims = []
    for dk in metric.dimensions:
        d = sem.dimension(dk)
        if d is None:
            continue
        dims.append({"key": d.key, "name": d.name, "type": _dim_catalog_type(d), "description": d.description})
    result = {
        "key": metric.key,
        "name": metric.name,
        "description": metric.description,
        "type": metric.type,
        "unit": metric.unit,
        "formula": metric.formula,
        "tables": metric.tables,
        "dimensions": dims,
        "constraints": _describe_constraints(metric),
        "concept": {"key": metric.concept, "name": _concept_name(metric.concept)},
        "access": {"allowed": reason is None, "reason": reason},
    }
    return _env.ok_envelope(persona.public_short(), result, {}, [])


def _describe_constraints(metric: Metric) -> list[dict]:
    keys = _constraints.constraint_keys_for(metric.key, metric.tables)
    out = []
    for c in _constraints._load_constraints():
        if c.get("key") in keys:
            out.append({"key": c["key"], "statement": c.get("statement", "")})
    return out


def _concept_name(concept_key: str) -> str:
    return concept_key.replace("-", " ").title()


def _dim_catalog_type(d) -> str:
    return d.type


# --- dimensions -------------------------------------------------------------


def dimensions_list(token: str) -> dict:
    sem, pol = _services()
    persona, err = _auth(pol, token)
    if err:
        return err
    access = pol.access_for(persona.role)
    dims = []
    for key, d in sem.dimensions.items():
        denial = access.dimension_denial(key)
        dims.append({
            "key": d.key,
            "name": d.name,
            "description": d.description,
            "type": _dim_catalog_type(d),
            "source": d.source,
            "access": {"allowed": denial is None, "reason": denial.reason if denial else None},
        })
    return _env.ok_envelope(persona.public_short(), {"dimensions": dims}, {}, [])


def dimensions_describe(key: str, token: str) -> dict:
    sem, pol = _services()
    persona, err = _auth(pol, token)
    if err:
        return err
    access = pol.access_for(persona.role)
    d = sem.dimension(key)
    if d is None:
        return _env.error_envelope(
            persona.public_short(), "INVALID_DIMENSION",
            f"'{key}' is not a governed dimension",
            {"dimension": key},
        )
    denial = access.dimension_denial(key)
    result = {
        "key": d.key,
        "name": d.name,
        "description": d.description,
        "type": _dim_catalog_type(d),
        "source": d.source,
        "canonical_values": sorted(d.canonical_values) if d.canonical_values else [],
        "grains": list(d.grains),
        "access": {"allowed": denial is None, "reason": denial.reason if denial else None},
    }
    return _env.ok_envelope(persona.public_short(), result, {}, [])


# --- query ------------------------------------------------------------------


def query(
    token: str, metric_key: str, *,
    group_by: list[str] | None = None,
    grain: str | None = None,
    filters: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = None,
) -> dict:
    sem, pol = _services()
    persona, err = _auth(pol, token)
    if err:
        return err
    access = pol.access_for(persona.role)

    metric = sem.metric(metric_key)
    if metric is None:
        return _metric_not_found(sem, persona, metric_key)

    # metric-level denial (table precedence over column)
    denial = access.metric_denial(metric_key)
    if denial is not None:
        return _denial_envelope(persona, denial, metric_key)

    limit = limit if limit is not None else 1000
    try:
        cq = compile_query(
            metric, sem, access, persona,
            group_by=group_by, grain=grain, filter_strs=filters,
            start=start, end=end, limit=limit,
        )
    except (CompileError, FilterError) as e:
        return _env.error_envelope(persona.public_short(), e.code, e.message, e.details)

    return _execute(sem, pol, persona, access, metric, cq, grain, start, end)


def _execute(sem, pol, persona, access, metric, cq: CompiledQuery, grain, start, end) -> dict:
    from query.engine import connect, list_tables

    warnings: list[dict] = []

    # data present?
    available = set(list_tables(DATA_DIR))
    missing = [t for t in metric.tables if t not in available]
    parquet_present = any((DATA_DIR / "parquet").glob("*.parquet")) if (DATA_DIR / "parquet").is_dir() else False
    if missing or not parquet_present:
        return _env.error_envelope(
            persona.public_short(), "INTERNAL",
            "warehouse data is not generated; run: cd source && uv run python -m generator.generate --scale small --seed 42",
            {"missing_tables": missing},
        )

    conn = connect(DATA_DIR)
    try:
        rel = conn.execute(cq.sql)
        raw_rows = rel.fetchall()
    except Exception as e:  # noqa: BLE001
        return _env.error_envelope(
            persona.public_short(), "INTERNAL", f"query execution failed: {e}", None
        )

    # column metadata + scalar coercion
    units = [c.unit for c in cq.columns]
    types = [c.type for c in cq.columns]
    tokenized_cols, banded_cols = _projection_transforms(sem, access, cq)

    try:
        rows = _coerce_rows(raw_rows, cq, units, tokenized_cols, banded_cols, warnings)
    except _env.NumberTooLarge as e:
        return _env.error_envelope(persona.public_short(), "INTERNAL", str(e), None)

    freshness, as_of, stale_warn = _freshness(conn, metric)
    if stale_warn:
        warnings.append(stale_warn)

    result = {
        "columns": [{"name": c.name, "type": c.type, "unit": c.unit} for c in cq.columns],
        "rows": rows,
        "row_count": len(rows),
    }
    if len(rows) >= cq.limit:
        warnings.append({"code": "ROW_LIMIT", "message": f"result truncated at limit {cq.limit}"})

    touched = set(metric.tables)
    metadata = {
        "as_of": as_of,
        "freshness": freshness,
        "applied_permissions": access.applied_permissions(persona, touched),
        "provenance": {
            "metric_key": metric.key,
            "metric_version": metric.version,
            "tables": metric.tables,
            "constraint_keys": _constraints.constraint_keys_for(metric.key, metric.tables),
            "compiled_sql": cq.sql,
        },
    }
    return _env.ok_envelope(persona.public_short(), result, metadata, warnings)


def _projection_transforms(sem, access: RoleAccess, cq: CompiledQuery):
    """Which output columns (by index) are tokenized / banded for the role."""
    tokenized: dict[int, tuple[str, int]] = {}
    banded: dict[int, str] = {}
    for i, col in enumerate(cq.columns):
        dim = sem.dimension(col.name)
        if dim is None or dim.source is None:
            continue
        if access.is_tokenized(dim.source):
            tok = access.semantic  # unused; keep prefix/length from policy
            tokenized[i] = ("cust_tok_", 12)
        elif access.transform_of(dim.source) == "band_5y":
            banded[i] = "band_5y"
    return tokenized, banded


def _coerce_rows(raw_rows, cq, units, tokenized_cols, banded_cols, warnings) -> list[list]:
    out = []
    for r in raw_rows:
        row = []
        for i, cell in enumerate(r):
            if i in tokenized_cols:
                prefix, length = tokenized_cols[i]
                row.append(_tok.tokenize(cell, prefix=prefix, length=length))
            elif i in banded_cols:
                row.append(_tok.band_5y(cell))
            else:
                unit = units[i]
                row.append(_env.coerce_by_unit(cell, unit, warnings))
        out.append(row)
    return out


def _freshness(conn, metric: Metric):
    """MAX date per touched table; as_of = min of those; STALE_DATA if they diverge."""
    schema = schema_module()
    fresh: dict[str, str] = {}
    for table in metric.tables:
        col = _time_col_for(schema, table)
        if col is None:
            continue
        try:
            val = conn.execute(f'SELECT MAX(CAST("{col}" AS DATE)) FROM "{table}"').fetchone()[0]
        except Exception:
            continue
        if val is not None:
            fresh[table] = val.isoformat() if hasattr(val, "isoformat") else str(val)
    if not fresh:
        return {}, None, None
    dates = sorted(fresh.values())
    as_of = dates[0]
    max_of = dates[-1]
    warn = None
    if as_of != max_of:
        warn = {
            "code": "STALE_DATA",
            "message": f"tables differ in freshness: earliest as_of {as_of}, latest {max_of}",
        }
    return fresh, as_of, warn


def _time_col_for(schema, table: str) -> str | None:
    """The date/timestamp column used for a table's freshness."""
    preferred = {
        "fact_sales_lines": "ts",
        "fact_returns": "return_date",
        "fact_inventory": "snapshot_date",
        "fact_traffic": "date",
        "dim_customer": "joined_date",
    }
    if table in preferred:
        return preferred[table]
    for c in schema.TABLES.get(table, []):
        if c.dtype in ("date", "timestamp"):
            return c.name
    return None


# --- error shapes -----------------------------------------------------------


def _metric_not_found(sem: SemanticLayer, persona, key: str) -> dict:
    candidates = _candidates(sem, key)
    if candidates:
        msg = (
            f"'{key}' is not a metric key; it matches multiple governed definitions "
            f"— ask the user which one"
        )
    else:
        msg = f"'{key}' is not a metric key"
    return _env.error_envelope(
        persona.public_short(), "METRIC_NOT_FOUND", msg, {"candidates": candidates}
    )


# The planted-ambiguity concept map (CONTRACT §4.3): a business term that fans out
# to multiple defensible metrics. These are the parent concepts whose variants the
# harness must disambiguate; on the warehouse surface an unresolved parent term
# comes back as METRIC_NOT_FOUND + candidates. Concept resolution proper lives in
# Agent B's graph; this curated map covers the warehouse-side candidate hints.
_CONCEPT_TERMS: dict[str, list[str]] = {
    "revenue": ["gmv_gross", "net_revenue"],
    "gmv": ["gmv_gross", "net_revenue"],
    "sales": ["gmv_gross", "net_revenue"],
    "topline": ["gmv_gross", "net_revenue"],
    "retention": ["repeat_purchase_rate_90d", "member_active_rate_30d"],
    "basket": ["basket_items_avg", "basket_value_avg"],
    "basket size": ["basket_items_avg", "basket_value_avg"],
}


def _candidates(sem: SemanticLayer, key: str) -> list[dict]:
    """Candidate metrics for a non-key term.

    First the curated ambiguity concepts (revenue/gmv -> gross+net, retention ->
    both retention metrics, basket -> items+value); then a substring fallback over
    metric keys/names/short descriptions.
    """
    q = key.lower().strip()

    concept_keys = _CONCEPT_TERMS.get(q)
    picked: list[str]
    if concept_keys:
        picked = [k for k in concept_keys if k in sem.metrics]
    else:
        picked = [
            m.key for m in sem.metrics.values()
            if any(q in h for h in (m.key.lower(), m.name.lower(), m.short_description.lower()))
        ]

    out = [
        {"key": m.key, "name": m.name, "definition": m.short_description}
        for m in (sem.metric(k) for k in picked) if m is not None
    ]
    out.sort(key=lambda c: c["key"])
    return out


def _denial_envelope(persona, denial, metric_key: str) -> dict:
    if denial.code == "ACCESS_DENIED_TABLE":
        return _env.error_envelope(
            persona.public_short(), "ACCESS_DENIED_TABLE",
            f"role {persona.role} cannot read table {denial.table}",
            {"table": denial.table, "reason": f"{denial.table} is not readable for role {persona.role}"},
        )
    return _env.error_envelope(
        persona.public_short(), "ACCESS_DENIED_METRIC",
        f"role {persona.role} cannot compute {metric_key}",
        {"reason": denial.reason},
    )

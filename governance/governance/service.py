"""Warehouse-surface command implementations for the `tn` CLI.

Serves: whoami, metrics list/describe, dimensions list/describe, query, and the
KG surface (kg schema/query via knowledge_graph.api).

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


POLICY_STORE_UNREACHABLE_MSG = (
    "policy store is not reachable; run: "
    "docker compose up --wait && uv run python -m governance.pg"
)


class PolicyStoreUnreachable(Exception):
    """Raised when the runtime policy store (Postgres) cannot be reached."""


def _services() -> tuple[SemanticLayer, Policy]:
    """Semantic layer (from disk) + runtime Policy (from Postgres, ADR 0010).

    users.yaml is still the authored source (load_policy), but the CLI reads the
    *runtime* policy from the Postgres store hydrated by `python -m governance.pg`.
    If the store is unreachable we raise PolicyStoreUnreachable; callers turn that
    into a clean INTERNAL envelope (mirrors the missing-warehouse-data pattern in
    _execute) rather than leaking a traceback.
    """
    from governance.pg import load_policy_from_db

    sem = load_semantic()
    try:
        pol = load_policy_from_db(semantic=sem)
    except Exception as e:  # noqa: BLE001 — any driver/connection failure is "unreachable"
        raise PolicyStoreUnreachable(str(e)) from e
    return sem, pol


def _policy_store_error_envelope() -> dict:
    return _env.error_envelope(None, "INTERNAL", POLICY_STORE_UNREACHABLE_MSG, None)


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


# --- knowledge graph ----------------------------------------------------------
# Imported lazily so the warehouse surface works without the kg package's
# neo4j dependency loaded.


def kg_schema() -> dict:
    """Graph self-description — tokenless per USING-TN; static payload."""
    from knowledge_graph import api as _kg

    return _env.ok_envelope(
        None, _kg.get_schema(), {"graph_compiled_at": _kg.compiled_at()}, []
    )


def kg_query(cypher: str, token: str) -> dict:
    """Read-only Cypher for the calling persona, `_access`-annotated (CONTRACT §4.4)."""
    from knowledge_graph import api as _kg
    from knowledge_graph.errors import InvalidQuery, QueryRejected

    sem, pol = _services()
    persona, err = _auth(pol, token)
    if err is not None:
        return err
    try:
        out = _kg.run_cypher(cypher, persona.role)
    except QueryRejected as e:
        return _env.error_envelope(
            persona.public_short(), "QUERY_REJECTED", e.message, {"reason": e.reason}
        )
    except InvalidQuery as e:
        return _env.error_envelope(
            persona.public_short(), "INVALID_QUERY", e.message, {"reason": e.message}
        )
    access = pol.access_for(persona.role)
    touched = _kg_touched_tables(out["records"], sem)
    metadata = {
        "graph_compiled_at": out["graph_compiled_at"],
        "applied_permissions": _kg_applied_permissions(access, persona, touched),
    }
    return _env.ok_envelope(persona.public_short(), {"records": out["records"]}, metadata, [])


def _kg_touched_tables(records, sem: SemanticLayer) -> set[str]:
    """Physical tables behind the governed nodes appearing anywhere in the records."""
    touched: set[str] = set()

    def walk(v):
        if isinstance(v, dict):
            label, key = v.get("_label"), v.get("key")
            if label == "Table" and key:
                touched.add(key)
            elif label == "Metric" and key:
                m = sem.metric(key)
                if m is not None:
                    touched.update(m.tables)
            elif label == "Dimension" and key:
                d = sem.dimension(key)
                if d is not None and d.table:
                    touched.add(d.table)
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(records)
    return touched


def _kg_applied_permissions(access, persona, touched: set[str]) -> list[dict]:
    """Truthful disclosure for the kg surface: only masked/banded columns on
    touched tables — they explain the `_access` annotations in the records.
    Row filters and tokenization govern row data, which a graph query never
    returns, so disclosing them here would be untruthful (per the
    kg-query-ok-access-annotation golden: lan's tokenized customer_id on the
    touched table is NOT disclosed, her cost mask is)."""
    applied: list[dict] = []
    for obj in access.permission_objects(persona):
        col = obj.get("column")
        if obj["type"] not in ("column_masked", "column_banded") or not col:
            continue
        if col.split(".", 1)[0] in touched:
            applied.append(obj)
    return applied

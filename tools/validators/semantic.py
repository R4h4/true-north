"""Semantic-layer validator — enforces source/semantic/SCHEMA.md.

Loads the metric/dimension YAML files under source/semantic/ and checks them
against source/generator/schema.py (the single source of truth for tables,
columns, and canonical value vocabularies). Returns a flat list of
human-readable error strings; empty means valid.
"""

from __future__ import annotations

from pathlib import Path

import sqlglot
import sqlglot.expressions as exp
import yaml

from tools.validators._schema_loader import load_schema as _load_schema

# Metric keys named in CONTRACT.md / contracts/examples that must exist as files.
CONTRACT_METRIC_KEYS = {
    "repeat_purchase_rate_90d",
    "member_active_rate_30d",
    "gmv_gross",
    "net_revenue",
    "basket_items_avg",
    "basket_value_avg",
    "gross_margin",
    "inventory_days",
}

METRIC_TYPES = {"sum", "count", "ratio", "derived"}
METRIC_UNITS = {"VND", "ratio", "count"}
DIM_TYPES = {"categorical", "time", "geo", "entity"}
AGGS = {"sum", "count", "count_distinct", "avg"}

REQUIRED_METRIC_FIELDS = (
    "key", "name", "short_description", "description", "concept",
    "type", "unit", "version", "formula", "time_dimension",
    "dimensions", "compute",
)

REQUIRED_TABLE_FIELDS = ("key", "description", "grain", "freshness_note")


def _canonical_vocab_map(schema) -> dict[str, set]:
    """table.column -> the set of canonical values schema.py promises for it."""
    return {
        "fact_sales_lines.channel": set(schema.CHANNELS),
        "dim_store.region": {"North", "Central", "South"},
        "dim_sku.category": set(schema.CATEGORIES.keys()),
        "dim_customer.tier": set(schema.CUSTOMER_TIERS),
        "dim_customer.customer_type": set(schema.CUSTOMER_TYPES),
        "dim_store.format": set(schema.STORE_FORMATS),
        "dim_store.province": set(schema.CANONICAL_PROVINCES),
        "dim_customer.province": set(schema.CANONICAL_PROVINCES),
        "fact_returns.reason": set(schema.RETURN_REASONS),
        "dim_promotion.mechanic": set(schema.PROMO_MECHANICS),
        "dim_promotion.funded_by": set(schema.PROMO_FUNDERS),
    }


def _columns_in_expr(expr: str) -> set[str]:
    """Bare column names referenced by a SQL expression (via sqlglot)."""
    tree = sqlglot.parse_one(expr, dialect="duckdb")
    return {col.name for col in tree.find_all(exp.Column)}


def _load_yaml_dir(directory: Path) -> dict[str, dict]:
    """filename stem -> parsed YAML doc for every *.yml in a directory."""
    docs: dict[str, dict] = {}
    if not directory.is_dir():
        return docs
    for path in sorted(directory.glob("*.yml")):
        docs[path.stem] = yaml.safe_load(path.read_text())
    return docs


def validate_semantic(
    semantic_dir: Path,
    schema_py: Path,
    required_metric_keys: set[str] | None = None,
) -> list[str]:
    semantic_dir = Path(semantic_dir)
    if required_metric_keys is None:
        required_metric_keys = CONTRACT_METRIC_KEYS

    schema = _load_schema(Path(schema_py))
    tables = schema.TABLES
    table_columns = {t: {c.name for c in cols} for t, cols in tables.items()}
    vocab_map = _canonical_vocab_map(schema)

    errors: list[str] = []

    metrics = _load_yaml_dir(semantic_dir / "metrics")
    dimensions = _load_yaml_dir(semantic_dir / "dimensions")
    table_docs = _load_yaml_dir(semantic_dir / "tables")

    # --- Dimensions -------------------------------------------------------
    dim_types: dict[str, str] = {}
    for stem, dim in dimensions.items():
        if not isinstance(dim, dict):
            errors.append(f"dimension {stem}.yml: not a mapping")
            continue
        key = dim.get("key")
        if key != stem:
            errors.append(f"dimension {stem}.yml: key '{key}' does not match filename '{stem}'")
        dtype = dim.get("type")
        dim_types[stem] = dtype
        if dtype not in DIM_TYPES:
            errors.append(f"dimension {stem}: type '{dtype}' not in {sorted(DIM_TYPES)}")

        source = dim.get("source")
        if dtype == "time":
            if source is not None:
                errors.append(f"dimension {stem}: type time must have null source")
        else:
            if not source:
                errors.append(f"dimension {stem}: source required for type {dtype}")
            elif "." not in str(source):
                errors.append(f"dimension {stem}: source '{source}' is not table.column")
            else:
                tbl, _, col = str(source).partition(".")
                if tbl not in tables:
                    errors.append(f"dimension {stem}: source table '{tbl}' not in schema.py")
                elif col not in table_columns[tbl]:
                    errors.append(f"dimension {stem}: source column '{source}' not in schema.py")

        if dtype == "categorical":
            cvals = dim.get("canonical_values")
            if cvals is None:
                errors.append(f"dimension {stem}: canonical_values required for categorical")
            elif source in vocab_map:
                expected = vocab_map[source]
                if set(cvals) != expected:
                    diff = set(cvals) ^ expected
                    errors.append(
                        f"dimension {stem}: canonical_values do not match schema.py vocabulary "
                        f"for {source}; differing values: {sorted(diff)}"
                    )
        if dtype == "time" and not dim.get("grains"):
            errors.append(f"dimension {stem}: grains required for type time")

    # --- Metrics ----------------------------------------------------------
    for stem, metric in metrics.items():
        if not isinstance(metric, dict):
            errors.append(f"metric {stem}.yml: not a mapping")
            continue
        key = metric.get("key")
        if key != stem:
            errors.append(f"metric {stem}.yml: key '{key}' does not match filename '{stem}'")

        for field in REQUIRED_METRIC_FIELDS:
            if field not in metric:
                errors.append(f"metric {stem}: missing required field '{field}'")

        mtype = metric.get("type")
        if mtype is not None and mtype not in METRIC_TYPES:
            errors.append(f"metric {stem}: type '{mtype}' not in {sorted(METRIC_TYPES)}")
        unit = metric.get("unit")
        if unit is not None and unit not in METRIC_UNITS:
            errors.append(f"metric {stem}: unit '{unit}' not in {sorted(METRIC_UNITS)}")
        if mtype == "ratio" and unit != "ratio":
            errors.append(f"metric {stem}: type ratio requires unit ratio (got '{unit}')")

        # time_dimension resolves and is time-typed
        tdim = metric.get("time_dimension")
        if tdim is not None:
            if tdim not in dimensions:
                errors.append(f"metric {stem}: time_dimension '{tdim}' is not a defined dimension")
            elif dim_types.get(tdim) != "time":
                errors.append(
                    f"metric {stem}: time_dimension '{tdim}' must be a dimension of type time"
                )

        for dkey in metric.get("dimensions") or []:
            if dkey not in dimensions:
                errors.append(f"metric {stem}: dimension '{dkey}' is not a defined dimension")

        errors.extend(_validate_compute(stem, metric, tables, table_columns))

    # --- Tables -----------------------------------------------------------
    for stem, table in table_docs.items():
        if not isinstance(table, dict):
            errors.append(f"table {stem}.yml: not a mapping")
            continue
        key = table.get("key")
        if key != stem:
            errors.append(f"table {stem}.yml: key '{key}' does not match filename '{stem}'")
        if key is not None and key not in tables:
            errors.append(f"table {stem}: key '{key}' is not a table in schema.py")
        for tfield in REQUIRED_TABLE_FIELDS:
            if not table.get(tfield):
                errors.append(f"table {stem}: missing required field '{tfield}'")

    # Every table referenced by a metric measure must have a tables/*.yml entry.
    referenced_tables: set[str] = set()
    for metric in metrics.values():
        if not isinstance(metric, dict):
            continue
        for measure in (metric.get("compute") or {}).get("measures", {}).values() or {}:
            if isinstance(measure, dict) and measure.get("table"):
                referenced_tables.add(measure["table"])
    for tbl in sorted(referenced_tables):
        if tbl not in table_docs:
            errors.append(
                f"table semantics: measure table '{tbl}' has no tables/{tbl}.yml entry"
            )

    # --- Required contract metrics exist ---------------------------------
    for req in sorted(required_metric_keys):
        if req not in metrics:
            errors.append(f"required contract metric '{req}' has no file in {semantic_dir}/metrics")

    return errors


def _validate_compute(stem, metric, tables, table_columns) -> list[str]:
    errors: list[str] = []
    compute = metric.get("compute")
    if not isinstance(compute, dict):
        return errors  # missing-field error already recorded
    measures = compute.get("measures") or {}

    for mname, measure in measures.items():
        if not isinstance(measure, dict):
            errors.append(f"metric {stem}: measure '{mname}' is not a mapping")
            continue
        mtable = measure.get("table")
        if mtable not in tables:
            errors.append(f"metric {stem}: measure '{mname}' references unknown table '{mtable}'")
            continue  # can't resolve columns without a valid table
        cols = table_columns[mtable]

        agg = measure.get("agg")
        if agg is not None and agg not in AGGS:
            errors.append(f"metric {stem}: measure '{mname}' agg '{agg}' invalid")

        # expr columns resolve against the measure table
        expr = measure.get("expr")
        if expr is not None:
            try:
                for col in _columns_in_expr(str(expr)):
                    if col not in cols:
                        errors.append(
                            f"metric {stem}: measure '{mname}' expr references unknown "
                            f"column '{col}' on table '{mtable}'"
                        )
            except Exception as e:  # noqa: BLE001 - surface parse failure as an error
                errors.append(f"metric {stem}: measure '{mname}' expr failed to parse: {e}")

        # time_column resolves
        tcol = measure.get("time_column")
        if tcol is not None and tcol not in cols:
            errors.append(
                f"metric {stem}: measure '{mname}' time_column '{tcol}' not on table '{mtable}'"
            )

        # filters columns resolve
        for filt in measure.get("filters") or []:
            fcol = filt.get("column") if isinstance(filt, dict) else None
            if fcol is not None and fcol not in cols:
                errors.append(
                    f"metric {stem}: measure '{mname}' filter column '{fcol}' not on table '{mtable}'"
                )

        # join tables and join columns resolve
        for join in measure.get("joins") or []:
            jtable = join.get("table")
            if jtable not in tables:
                errors.append(
                    f"metric {stem}: measure '{mname}' join references unknown table '{jtable}'"
                )
            for side in ("left_on", "right_on"):
                ref = join.get(side)
                if ref is None:
                    continue
                # ref may be qualified (table.column) or bare
                if "." in str(ref):
                    jt, _, jc = str(ref).partition(".")
                    if jt not in tables:
                        errors.append(
                            f"metric {stem}: measure '{mname}' join {side} table '{jt}' unknown"
                        )
                    elif jc not in table_columns[jt]:
                        errors.append(
                            f"metric {stem}: measure '{mname}' join {side} column '{ref}' unknown"
                        )

    # compute.expr references declared measures only; every declared measure referenced
    top_expr = compute.get("expr")
    if top_expr is not None and measures:
        try:
            referenced = _columns_in_expr(str(top_expr))
        except Exception as e:  # noqa: BLE001
            errors.append(f"metric {stem}: compute.expr failed to parse: {e}")
            referenced = set()
        declared = set(measures.keys())
        for ref in referenced:
            if ref not in declared:
                errors.append(
                    f"metric {stem}: compute.expr references undeclared measure '{ref}'"
                )
        for decl in sorted(declared):
            if decl not in referenced:
                errors.append(
                    f"metric {stem}: declared measure '{decl}' is never referenced in compute.expr"
                )

    return errors

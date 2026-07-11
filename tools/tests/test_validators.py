"""Validator tests — written first; the validators are implemented against these.

Expected API (implement in tools/validators/):

    validate_semantic(semantic_dir: Path, schema_py: Path,
                      required_metric_keys: set[str] | None = None) -> list[str]
        # None -> CONTRACT_METRIC_KEYS (the metric keys named in CONTRACT.md/goldens)
    validate_vocabulary(vocab_dir: Path, semantic_dir: Path, schema_py: Path) -> list[str]
    validate_policy(users_yaml: Path, schema_py: Path) -> list[str]
    tools.validate.main(argv: list[str] | None = None) -> int   # 0 clean, 1 errors

Each returns a flat list of human-readable error strings (empty == valid).
Schemas under test: source/semantic/SCHEMA.md, knowledge-graph/vocabulary/SCHEMA.md,
governance/POLICY.md. Error-message assertions are loose (substring) on purpose.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml
import pytest

from tools.validators.semantic import CONTRACT_METRIC_KEYS, validate_semantic
from tools.validators.vocabulary import validate_vocabulary
from tools.validators.policy import validate_policy

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PY = REPO_ROOT / "source" / "generator" / "schema.py"


# ---------------------------------------------------------------------------
# Baseline fixtures (minimal valid set; individual tests mutate copies)
# ---------------------------------------------------------------------------

DIM_CHANNEL = {
    "key": "channel",
    "name": "Sales channel",
    "description": "Transaction channel as recorded at point of sale.",
    "type": "categorical",
    "source": "fact_sales_lines.channel",
    "canonical_values": ["in_store", "web", "app", "b2b"],
}

DIM_DATE = {
    "key": "date",
    "name": "Date",
    "description": "Business date of the underlying event.",
    "type": "time",
    "source": None,
    "grains": ["day", "week", "month", "quarter", "year"],
}

METRIC_NET_REVENUE = {
    "key": "net_revenue",
    "name": "Net revenue",
    "short_description": "Revenue net of discounts and returns.",
    "description": "Booked revenue net of line discounts, minus refunds from fact_returns.",
    "concept": "net-revenue",
    "type": "derived",
    "unit": "VND",
    "version": "0.1",
    "formula": "SUM(net_amount) - SUM(refund_amount)",
    "time_dimension": "date",
    "dimensions": ["channel"],
    "compute": {
        "measures": {
            "sales_net": {
                "table": "fact_sales_lines",
                "expr": "net_amount",
                "agg": "sum",
                "time_column": "ts",
            },
            "returns_refund": {
                "table": "fact_returns",
                "expr": "refund_amount",
                "agg": "sum",
                "time_column": "return_date",
                "joins": [
                    {"table": "fact_sales_lines", "left_on": "orig_basket_id", "right_on": "basket_id"}
                ],
            },
        },
        "expr": "sales_net - returns_refund",
    },
}

CONCEPT_PARENT = {
    "key": "gmv-revenue",
    "name": "GMV / Revenue",
    "definition": "Umbrella term for topline sales value; ambiguous between gross and net.",
    "aliases": ["revenue", "gmv", "topline"],
    "variant_of": None,
    "measured_by": None,
}

CONCEPT_VARIANT = {
    "key": "net-revenue",
    "name": "Net revenue",
    "definition": "Revenue after discounts and returns.",
    "aliases": ["net sales"],
    "variant_of": "gmv-revenue",
    "measured_by": "net_revenue",
}

CONSTRAINT_B2B = {
    "key": "b2b_value_skew",
    "statement": "B2B baskets skew value-based averages; split channel b2b out.",
    "severity": "warning",
    "constrains": ["metric:net_revenue", "table:fact_sales_lines"],
}

USERS_BASE = {
    "users": [
        {"token": "tok-exec-mai", "user_id": "u_mai", "name": "Mai", "title": "CEO", "role": "executive"},
        {
            "token": "tok-rm-south-duc",
            "user_id": "u_duc",
            "name": "Duc",
            "title": "RM South",
            "role": "regional_manager",
            "attributes": {"region": "South"},
        },
        {"token": "tok-mkt-lan", "user_id": "u_lan", "name": "Lan", "title": "Marketing", "role": "marketing_ops"},
        {"token": "tok-analyst-binh", "user_id": "u_binh", "name": "Binh", "title": "Analyst", "role": "data_analyst"},
    ],
    "roles": {
        "executive": {
            "description": "full",
            "tables": "all",
            "row_filters": [],
            "masked_columns": [],
            "tokenized_columns": ["fact_sales_lines.customer_id"],
        },
        "regional_manager": {
            "description": "region-scoped",
            "tables": "all",
            "row_filters": [
                {
                    "tables": ["fact_sales_lines"],
                    "predicate": "store_id IN (SELECT store_id FROM dim_store WHERE region = '{region}')",
                    "discloses_as": "dim_store.region = '{region}'",
                }
            ],
            "masked_columns": ["dim_customer.province"],
            "tokenized_columns": [],
        },
        "marketing_ops": {
            "description": "no inventory, no cost",
            "tables": [
                "dim_store", "dim_sku", "dim_customer", "dim_promotion",
                "fact_sales_lines", "fact_returns", "fact_traffic",
            ],
            "row_filters": [],
            "masked_columns": ["fact_sales_lines.cost_amount"],
            "tokenized_columns": [],
            "transformed_columns": [{"column": "dim_customer.birth_year", "transform": "band_5y"}],
        },
        "data_analyst": {
            "description": "full, tokenized ids",
            "tables": "all",
            "row_filters": [],
            "masked_columns": [],
            "tokenized_columns": ["fact_sales_lines.customer_id"],
        },
    },
    "tokenization": {"scheme": "hmac_sha256_prefix", "prefix": "cust_tok_", "length": 12},
}


TABLE_SALES = {
    "key": "fact_sales_lines",
    "description": "One row per basket line; net_amount is booked (gross of returns).",
    "grain": "sales line",
    "freshness_note": "refreshed daily",
}
TABLE_RETURNS = {
    "key": "fact_returns",
    "description": "Refunds; refund_amount reduces net revenue.",
    "grain": "return line",
    "freshness_note": "refreshed daily",
}


def write_semantic(
    tmp: Path,
    metrics: dict[str, dict],
    dimensions: dict[str, dict],
    tables: dict[str, dict] | None = None,
) -> Path:
    root = tmp / "semantic"
    groups = [("metrics", metrics), ("dimensions", dimensions)]
    if tables is not None:
        groups.append(("tables", tables))
    for sub, items in groups:
        (root / sub).mkdir(parents=True, exist_ok=True)
        for name, doc in items.items():
            (root / sub / f"{name}.yml").write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return root


def write_vocab(tmp: Path, concepts: dict[str, dict], constraints: dict[str, dict]) -> Path:
    root = tmp / "vocabulary"
    for sub, items in (("concepts", concepts), ("constraints", constraints)):
        (root / sub).mkdir(parents=True, exist_ok=True)
        for name, doc in items.items():
            (root / sub / f"{name}.yml").write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return root


def write_users(tmp: Path, doc: dict) -> Path:
    p = tmp / "users.yaml"
    p.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True))
    return p


def base_semantic(tmp: Path, metric_mut=None, dim_mut=None, table_mut=None, metric_name="net_revenue") -> Path:
    metric = copy.deepcopy(METRIC_NET_REVENUE)
    if metric_mut:
        metric_mut(metric)
    dims = {"channel": copy.deepcopy(DIM_CHANNEL), "date": copy.deepcopy(DIM_DATE)}
    if dim_mut:
        dim_mut(dims)
    tables = {
        "fact_sales_lines": copy.deepcopy(TABLE_SALES),
        "fact_returns": copy.deepcopy(TABLE_RETURNS),
    }
    if table_mut:
        table_mut(tables)
    return write_semantic(tmp, {metric_name: metric}, dims, tables)


BASE_KEYS = {"net_revenue"}


# ---------------------------------------------------------------------------
# Semantic-layer validator
# ---------------------------------------------------------------------------

class TestSemanticValidator:
    def test_baseline_is_valid(self, tmp_path):
        root = base_semantic(tmp_path)
        assert validate_semantic(root, SCHEMA_PY, required_metric_keys=BASE_KEYS) == []

    def test_contract_metric_keys_constant(self):
        assert CONTRACT_METRIC_KEYS == {
            "repeat_purchase_rate_90d", "member_active_rate_30d",
            "gmv_gross", "net_revenue",
            "basket_items_avg", "basket_value_avg",
            "gross_margin", "inventory_days",
        }

    def test_missing_required_field(self, tmp_path):
        root = base_semantic(tmp_path, metric_mut=lambda m: m.pop("formula"))
        errors = validate_semantic(root, SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("formula" in e for e in errors)

    def test_key_must_match_filename(self, tmp_path):
        root = base_semantic(tmp_path, metric_name="wrong_file_name")
        errors = validate_semantic(root, SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("wrong_file_name" in e for e in errors)

    def test_unknown_measure_table(self, tmp_path):
        def mut(m):
            m["compute"]["measures"]["sales_net"]["table"] = "fact_bogus"
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("fact_bogus" in e for e in errors)

    def test_unknown_column_in_expr(self, tmp_path):
        def mut(m):
            m["compute"]["measures"]["sales_net"]["expr"] = "net_amount - bogus_col"
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("bogus_col" in e for e in errors)

    def test_unknown_time_column(self, tmp_path):
        def mut(m):
            m["compute"]["measures"]["sales_net"]["time_column"] = "no_such_date"
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("no_such_date" in e for e in errors)

    def test_undefined_dimension_key(self, tmp_path):
        def mut(m):
            m["dimensions"] = ["channel", "ghost_dim"]
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("ghost_dim" in e for e in errors)

    def test_time_dimension_must_be_time_typed(self, tmp_path):
        def mut(m):
            m["time_dimension"] = "channel"
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("time" in e for e in errors)

    def test_ratio_type_requires_ratio_unit(self, tmp_path):
        def mut(m):
            m["type"] = "ratio"
            m["unit"] = "VND"
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("ratio" in e for e in errors)

    def test_compute_expr_references_declared_measures_only(self, tmp_path):
        def mut(m):
            m["compute"]["expr"] = "sales_net - phantom_measure"
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("phantom_measure" in e for e in errors)

    def test_unreferenced_measure_is_an_error(self, tmp_path):
        def mut(m):
            m["compute"]["expr"] = "sales_net"
        errors = validate_semantic(base_semantic(tmp_path, metric_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("returns_refund" in e for e in errors)

    def test_canonical_values_must_match_schema_vocabulary(self, tmp_path):
        def mut(dims):
            dims["channel"]["canonical_values"] = ["in_store", "web", "app", "b2b", "offline"]
        errors = validate_semantic(base_semantic(tmp_path, dim_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("offline" in e for e in errors)

    def test_required_contract_metrics_must_exist(self, tmp_path):
        root = base_semantic(tmp_path)
        errors = validate_semantic(root, SCHEMA_PY, required_metric_keys={"net_revenue", "gmv_gross"})
        assert any("gmv_gross" in e for e in errors)

    def test_table_key_must_resolve_to_schema(self, tmp_path):
        def mut(tables):
            tables["fact_bogus"] = {
                "key": "fact_bogus",
                "description": "x",
                "grain": "y",
                "freshness_note": "z",
            }
        errors = validate_semantic(base_semantic(tmp_path, table_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("fact_bogus" in e for e in errors)

    def test_table_key_must_match_filename(self, tmp_path):
        def mut(tables):
            tables["fact_sales_lines"]["key"] = "wrong_key"
        errors = validate_semantic(base_semantic(tmp_path, table_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("wrong_key" in e for e in errors)

    def test_table_missing_required_field(self, tmp_path):
        def mut(tables):
            tables["fact_sales_lines"].pop("grain")
        errors = validate_semantic(base_semantic(tmp_path, table_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("grain" in e and "fact_sales_lines" in e for e in errors)

    def test_measure_table_must_have_tables_entry(self, tmp_path):
        # net_revenue's returns_refund measure reads fact_returns; drop its tables entry.
        def mut(tables):
            del tables["fact_returns"]
        errors = validate_semantic(base_semantic(tmp_path, table_mut=mut), SCHEMA_PY, required_metric_keys=BASE_KEYS)
        assert any("fact_returns" in e for e in errors)


# ---------------------------------------------------------------------------
# Vocabulary validator
# ---------------------------------------------------------------------------

class TestVocabularyValidator:
    def _semantic(self, tmp_path) -> Path:
        return base_semantic(tmp_path)

    def _run(self, tmp_path, concepts=None, constraints=None):
        vocab = write_vocab(
            tmp_path,
            concepts if concepts is not None
            else {"gmv-revenue": copy.deepcopy(CONCEPT_PARENT), "net-revenue": copy.deepcopy(CONCEPT_VARIANT)},
            constraints if constraints is not None
            else {"b2b_value_skew": copy.deepcopy(CONSTRAINT_B2B)},
        )
        return validate_vocabulary(vocab, self._semantic(tmp_path), SCHEMA_PY)

    def test_baseline_is_valid(self, tmp_path):
        assert self._run(tmp_path) == []

    def test_variant_requires_measured_by(self, tmp_path):
        variant = copy.deepcopy(CONCEPT_VARIANT)
        variant["measured_by"] = None
        errors = self._run(tmp_path, concepts={"gmv-revenue": copy.deepcopy(CONCEPT_PARENT), "net-revenue": variant})
        assert any("measured_by" in e for e in errors)

    def test_parent_must_not_have_measured_by(self, tmp_path):
        parent = copy.deepcopy(CONCEPT_PARENT)
        parent["measured_by"] = "net_revenue"
        errors = self._run(tmp_path, concepts={"gmv-revenue": parent, "net-revenue": copy.deepcopy(CONCEPT_VARIANT)})
        assert any("parent" in e.lower() for e in errors)

    def test_measured_by_must_resolve_to_semantic_metric(self, tmp_path):
        variant = copy.deepcopy(CONCEPT_VARIANT)
        variant["measured_by"] = "no_such_metric"
        errors = self._run(tmp_path, concepts={"gmv-revenue": copy.deepcopy(CONCEPT_PARENT), "net-revenue": variant})
        assert any("no_such_metric" in e for e in errors)

    def test_measured_by_is_one_to_one(self, tmp_path):
        second = copy.deepcopy(CONCEPT_VARIANT)
        second["key"] = "booked-revenue"
        second["name"] = "Booked revenue"
        second["aliases"] = []
        errors = self._run(
            tmp_path,
            concepts={
                "gmv-revenue": copy.deepcopy(CONCEPT_PARENT),
                "net-revenue": copy.deepcopy(CONCEPT_VARIANT),
                "booked-revenue": second,
            },
        )
        assert any("net_revenue" in e for e in errors)

    def test_variant_of_must_resolve(self, tmp_path):
        variant = copy.deepcopy(CONCEPT_VARIANT)
        variant["variant_of"] = "ghost-parent"
        errors = self._run(tmp_path, concepts={"gmv-revenue": copy.deepcopy(CONCEPT_PARENT), "net-revenue": variant})
        assert any("ghost-parent" in e for e in errors)

    def test_no_variant_chains(self, tmp_path):
        parent = copy.deepcopy(CONCEPT_PARENT)
        parent["variant_of"] = "net-revenue"  # parent is itself a variant -> chain
        errors = self._run(tmp_path, concepts={"gmv-revenue": parent, "net-revenue": copy.deepcopy(CONCEPT_VARIANT)})
        assert errors

    def test_alias_uniqueness_case_insensitive(self, tmp_path):
        variant = copy.deepcopy(CONCEPT_VARIANT)
        variant["aliases"] = ["Revenue"]  # parent already claims "revenue"
        errors = self._run(tmp_path, concepts={"gmv-revenue": copy.deepcopy(CONCEPT_PARENT), "net-revenue": variant})
        assert any("revenue" in e.lower() for e in errors)

    def test_constraint_severity_enum(self, tmp_path):
        bad = copy.deepcopy(CONSTRAINT_B2B)
        bad["severity"] = "catastrophic"
        errors = self._run(tmp_path, constraints={"b2b_value_skew": bad})
        assert any("catastrophic" in e for e in errors)

    def test_constraint_targets_must_resolve(self, tmp_path):
        bad = copy.deepcopy(CONSTRAINT_B2B)
        bad["constrains"] = ["metric:ghost_metric"]
        errors = self._run(tmp_path, constraints={"b2b_value_skew": bad})
        assert any("ghost_metric" in e for e in errors)

    def test_constraint_target_kind_enum(self, tmp_path):
        bad = copy.deepcopy(CONSTRAINT_B2B)
        bad["constrains"] = ["role:executive"]
        errors = self._run(tmp_path, constraints={"b2b_value_skew": bad})
        assert any("role" in e for e in errors)


# ---------------------------------------------------------------------------
# Policy validator
# ---------------------------------------------------------------------------

class TestPolicyValidator:
    def test_baseline_is_valid(self, tmp_path):
        assert validate_policy(write_users(tmp_path, copy.deepcopy(USERS_BASE)), SCHEMA_PY) == []

    def test_real_repo_users_yaml_is_valid(self):
        users = REPO_ROOT / "governance" / "fixtures" / "users.yaml"
        assert validate_policy(users, SCHEMA_PY) == []

    def test_all_four_contract_roles_required(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        del doc["roles"]["marketing_ops"]
        doc["users"] = [u for u in doc["users"] if u["role"] != "marketing_ops"]
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("marketing_ops" in e for e in errors)

    def test_all_four_contract_tokens_required(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        doc["users"] = [u for u in doc["users"] if u["token"] != "tok-analyst-binh"]
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("tok-analyst-binh" in e for e in errors)

    def test_user_role_must_be_declared(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        doc["users"][0]["role"] = "superadmin"
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("superadmin" in e for e in errors)

    def test_unknown_table_in_grants(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        doc["roles"]["marketing_ops"]["tables"].append("fact_bogus")
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("fact_bogus" in e for e in errors)

    def test_unknown_column_in_masked(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        doc["roles"]["marketing_ops"]["masked_columns"].append("dim_customer.ssn")
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("ssn" in e for e in errors)

    def test_column_in_at_most_one_treatment(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        doc["roles"]["marketing_ops"]["masked_columns"].append("dim_customer.birth_year")
        # birth_year is already in transformed_columns for marketing_ops
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("birth_year" in e for e in errors)

    def test_predicate_placeholders_must_resolve_from_user_attributes(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        doc["users"][1].pop("attributes")  # duc loses {region}
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("region" in e for e in errors)

    def test_transform_enum(self, tmp_path):
        doc = copy.deepcopy(USERS_BASE)
        doc["roles"]["marketing_ops"]["transformed_columns"][0]["transform"] = "rot13"
        errors = validate_policy(write_users(tmp_path, doc), SCHEMA_PY)
        assert any("rot13" in e for e in errors)


# ---------------------------------------------------------------------------
# CLI entrypoint
# ---------------------------------------------------------------------------

class TestValidateCli:
    def test_main_returns_int(self):
        from tools.validate import main
        rc = main([])
        assert rc in (0, 1)

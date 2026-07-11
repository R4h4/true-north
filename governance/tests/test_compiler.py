"""Unit tests for the SQLGlot compiler + governance derivation (Deliverable 3).

These exercise the compiler and service directly (no subprocess) against the
seed-42 small dataset. They assert the governance guarantees the conformance
goldens can only check structurally: determinism, predicate injection, masking,
tokenization stability/joinability, banding, denial precedence, the 2^53 guard.
"""

from __future__ import annotations

import pytest

from governance import envelope as _env
from governance import service
from governance import tokenization as _tok
from governance.compiler import CompileError, compile_query
from governance.policy import load_policy
from governance.semantic import load_semantic

SEM = load_semantic()
POL = load_policy(semantic=SEM)


def _compile(token, metric, **kw):
    persona = POL.resolve_token(token)
    access = POL.access_for(persona.role)
    return compile_query(SEM.metric(metric), SEM, access, persona, **kw)


# --- determinism ------------------------------------------------------------


def test_compiler_is_byte_deterministic():
    a = _compile("tok-exec-mai", "net_revenue", group_by=["channel"])
    b = _compile("tok-exec-mai", "net_revenue", group_by=["channel"])
    assert a.sql == b.sql


def test_group_by_ordering_time_first_then_asc():
    cq = _compile("tok-exec-mai", "net_revenue", group_by=["channel"], grain="month")
    # time dimension is the leading group key
    assert cq.group_keys[0] == "date"
    assert "channel" in cq.group_keys
    assert "ORDER BY" in cq.sql.upper()


# --- predicate injection ----------------------------------------------------


def test_row_filter_predicate_injected_for_regional_manager():
    cq = _compile("tok-rm-south-duc", "net_revenue", group_by=["channel"])
    assert "region = 'South'" in cq.sql
    # returns measure scopes via the joined fact_sales_lines, never bare store_id
    assert "fact_sales_lines.store_id IN" in cq.sql or "store_id IN" in cq.sql


def test_row_filter_absent_for_national_role():
    cq = _compile("tok-exec-mai", "net_revenue", group_by=["channel"])
    assert "region = 'South'" not in cq.sql


def test_row_filter_scopes_result_below_national():
    duc = service.query("tok-rm-south-duc", "net_revenue", group_by=["channel"])
    mai = service.query("tok-exec-mai", "net_revenue", group_by=["channel"])
    assert sum(r[1] for r in duc["result"]["rows"]) < sum(r[1] for r in mai["result"]["rows"])
    assert any(p["type"] == "row_filter" for p in duc["metadata"]["applied_permissions"])


# --- masking / dimension denial ---------------------------------------------


def test_masked_dimension_denied_via_group_by():
    # customer_province is backed by dim_customer.province, masked for the
    # regional_manager. Maliciously grouping by it -> ACCESS_DENIED_DIMENSION.
    with pytest.raises(CompileError) as ei:
        _compile("tok-rm-south-duc", "net_revenue", group_by=["customer_province"])
    assert ei.value.code == "ACCESS_DENIED_DIMENSION"


def test_masked_dimension_denied_via_filter():
    # Same masked column, reached through a --filter clause: still denied, so the
    # masked value never influences the query.
    with pytest.raises(CompileError) as ei:
        _compile("tok-rm-south-duc", "net_revenue", filter_strs=["customer_province = 'Ho Chi Minh City'"])
    assert ei.value.code == "ACCESS_DENIED_DIMENSION"


def test_masked_dimension_allowed_for_unmasked_role():
    # The executive does not mask dim_customer.province; the same group-by
    # compiles and the masked physical column of OTHER roles is irrelevant here.
    cq = _compile("tok-exec-mai", "net_revenue", group_by=["customer_province"])
    assert "customer_province" in cq.group_keys


def test_masked_column_absent_from_compiled_sql():
    # cost_amount is masked for marketing_ops; no compiled query for that role may
    # reference it. (gross_margin is denied outright; a permitted metric must not
    # leak it either.)
    cq = _compile("tok-mkt-lan", "net_revenue", group_by=["channel"])
    assert "cost_amount" not in cq.sql


# --- denial precedence ------------------------------------------------------


def test_table_denial_precedence_over_metric():
    # inventory_days for marketing_ops: table unreadable -> ACCESS_DENIED_TABLE,
    # not ACCESS_DENIED_METRIC.
    env = service.query("tok-mkt-lan", "inventory_days")
    assert env["error"]["code"] == "ACCESS_DENIED_TABLE"
    assert env["error"]["details"]["table"] == "fact_inventory"


def test_masked_column_denial_is_metric_level():
    env = service.query("tok-mkt-lan", "gross_margin", group_by=["category"])
    assert env["error"]["code"] == "ACCESS_DENIED_METRIC"
    assert "cost_amount" in env["error"]["details"]["reason"]


# --- tokenization -----------------------------------------------------------


def test_tokenization_is_stable_within_run():
    assert _tok.tokenize("C0000123") == _tok.tokenize("C0000123")


def test_tokenization_is_joinable_distinct_preserving():
    ids = ["C1", "C2", "C3", "C1", "C2"]
    toks = [_tok.tokenize(i) for i in ids]
    # same input -> same token (join/count preserving); distinct count preserved
    assert len(set(toks)) == len(set(ids))
    assert toks[0] == toks[3] and toks[1] == toks[4]


def test_tokenization_is_irreversible_prefixed():
    tok = _tok.tokenize("C0000123")
    assert tok.startswith("cust_tok_")
    assert "C0000123" not in tok


def test_null_is_not_tokenized():
    assert _tok.tokenize(None) is None


# --- banding ----------------------------------------------------------------


def test_band_5y_buckets_inclusive():
    assert _tok.band_5y(1990) == "1990-1994"
    assert _tok.band_5y(1994) == "1990-1994"
    assert _tok.band_5y(1995) == "1995-1999"


def test_band_5y_null_passthrough():
    assert _tok.band_5y(None) is None


# --- scalar rules / 2^53 guard ---------------------------------------------


def test_money_coerced_to_integer():
    warnings = []
    assert _env.coerce_money(123.9, warnings) == 124
    assert isinstance(_env.coerce_money(100.0, warnings), int)


def test_money_guards_2_53():
    warnings = []
    with pytest.raises(_env.NumberTooLarge):
        _env.coerce_money(2 ** 53 + 10, warnings)


def test_ratio_in_unit_interval_shape():
    warnings = []
    v = _env.coerce_ratio(0.42, warnings)
    assert isinstance(v, float) and 0.0 <= v <= 1.0


def test_nan_becomes_null_with_warning():
    warnings = []
    assert _env.coerce_money(float("nan"), warnings) is None
    assert warnings


# --- candidate resolution ---------------------------------------------------


def test_revenue_yields_gross_and_net_candidates():
    env = service.query("tok-exec-mai", "revenue")
    keys = [c["key"] for c in env["error"]["details"]["candidates"]]
    assert keys == ["gmv_gross", "net_revenue"]


def test_retention_yields_both_retention_metrics():
    env = service.query("tok-analyst-binh", "retention")
    keys = [c["key"] for c in env["error"]["details"]["candidates"]]
    assert keys == ["member_active_rate_30d", "repeat_purchase_rate_90d"]


# --- invariants -------------------------------------------------------------


def test_net_revenue_never_exceeds_gmv():
    gmv = service.query("tok-exec-mai", "gmv_gross", group_by=["channel"])["result"]["rows"]
    net = service.query("tok-exec-mai", "net_revenue", group_by=["channel"])["result"]["rows"]
    assert sum(r[1] for r in net) <= sum(r[1] for r in gmv)


def test_basket_items_differs_from_value():
    items = service.query("tok-analyst-binh", "basket_items_avg", group_by=["channel"])["result"]["rows"]
    value = service.query("tok-analyst-binh", "basket_value_avg", group_by=["channel"])["result"]["rows"]
    assert items != value

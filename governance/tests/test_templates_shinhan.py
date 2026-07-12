"""Regression tests for the shinhan fpd_rate template (demo bug, 2026-07-12).

Demo repro: `tn --dataset shinhan query --metric fpd_rate --group-by product`
returned INTERNAL "no template builder for 'fpd_rate'" — the metric YAML declares
`compute.template: fpd_rate` but governance.templates only had the five retail
builders. These tests compile the vintage metric directly (YAML policy, no
Postgres) and, when the generated shinhan parquet exists, execute it on DuckDB.
"""

from __future__ import annotations

import pytest

from governance.compiler import CompileError, compile_query
from governance.policy import load_policy
from semantic_layer import load_semantic
from semantic_layer.datasets import get_dataset

DS = get_dataset("shinhan")
SEM = load_semantic(DS.semantic_dir)
POL = load_policy(DS.users_yaml, semantic=SEM, dataset="shinhan")

PRODUCTS = {"cash_loan", "cd_installment", "two_wheeler_loan", "credit_card_loan"}


def _compile(token, metric, **kw):
    persona = POL.resolve_token(token)
    access = POL.access_for(persona.role)
    return compile_query(SEM.metric(metric), SEM, access, persona, **kw)


# --- the demo repro ----------------------------------------------------------


def test_fpd_rate_by_product_compiles():
    cq = _compile("tok-exec-sujin", "fpd_rate", group_by=["product"])
    low = cq.sql.lower()
    assert "fact_disbursements" in low
    assert "fact_loan_snapshots" in low
    assert cq.group_keys == ["product"]


def test_fpd_rate_numerator_is_dpd30_within_two_snapshot_months():
    cq = _compile("tok-exec-sujin", "fpd_rate", group_by=["product"])
    low = cq.sql.lower()
    assert "dpd >= 30" in low
    # vintage window: snapshot month relative to the disbursement month
    assert "disbursed_date" in low and "snapshot_month" in low


def test_fpd_rate_is_byte_deterministic():
    a = _compile("tok-exec-sujin", "fpd_rate", group_by=["product"])
    b = _compile("tok-exec-sujin", "fpd_rate", group_by=["product"])
    assert a.sql == b.sql


# --- vintage semantics -------------------------------------------------------


def test_fpd_rate_time_bounds_bind_to_vintage_not_snapshot():
    cq = _compile(
        "tok-exec-sujin", "fpd_rate", group_by=["product"],
        start="2024-01-01", end="2024-12-31",
    )
    low = cq.sql.lower()
    assert "cast(disbursed_date as date) >= '2024-01-01'" in low
    assert "cast(disbursed_date as date) <= '2024-12-31'" in low
    assert "cast(snapshot_month as date) >= " not in low


def test_fpd_rate_grain_month_groups_by_vintage_month():
    cq = _compile("tok-exec-sujin", "fpd_rate", grain="month")
    assert cq.group_keys[0] == "vintage_month"
    assert "date_trunc" in cq.sql.lower()


# --- governance --------------------------------------------------------------


def test_fpd_rate_row_filter_injected_for_collections_role():
    cq = _compile("tok-coll-thao", "fpd_rate", group_by=["product"])
    assert "province in" in cq.sql.lower()


def test_fpd_rate_row_filter_absent_for_executive():
    cq = _compile("tok-exec-sujin", "fpd_rate", group_by=["product"])
    assert "province" not in cq.sql.lower()


def test_fpd_rate_channel_filter_uses_native_column():
    cq = _compile(
        "tok-exec-sujin", "fpd_rate", group_by=["product"],
        filter_strs=["channel = 'digital_app'"],
    )
    low = cq.sql.lower()
    assert "'digital_app'" in low
    assert "channel_key" not in low  # dim source column is not on fact_disbursements


def test_fpd_rate_undeclared_dimension_rejected():
    with pytest.raises(CompileError) as e:
        _compile("tok-exec-sujin", "fpd_rate", group_by=["province"])
    assert e.value.code == "INVALID_DIMENSION"


# --- execution (needs generated shinhan parquet) ------------------------------

_HAS_DATA = (DS.data_dir / "parquet").is_dir() and any(
    (DS.data_dir / "parquet").glob("*.parquet")
)


@pytest.mark.skipif(not _HAS_DATA, reason="shinhan parquet not generated (make demo)")
def test_fpd_rate_executes_with_plausible_ratios():
    from query.engine import connect, run_query

    cq = _compile("tok-exec-sujin", "fpd_rate", group_by=["product"])
    rows = run_query(connect(DS.data_dir), cq.sql).fetchall()
    assert 1 <= len(rows) <= len(PRODUCTS)
    for product, rate in rows:
        assert product in PRODUCTS
        assert rate is None or 0.0 <= rate <= 1.0
    # calibrated book: FPD is small but not zero across every product
    assert any(rate and rate > 0 for _, rate in rows)

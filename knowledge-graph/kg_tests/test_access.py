"""Access derivation matches the CONTRACT §1 persona behavior (POLICY.md rules)."""

from __future__ import annotations


def test_marketing_ops_denied_inventory_table(access_index):
    acc = access_index.table_access("fact_inventory", "marketing_ops")
    assert acc["readable"] is False
    assert "fact_inventory" in acc["reason"]


def test_marketing_ops_reads_sales(access_index):
    assert access_index.table_access("fact_sales_lines", "marketing_ops")["readable"] is True


def test_all_roles_read_sales_except_none(access_index):
    for role in ("executive", "regional_manager", "marketing_ops", "data_analyst"):
        assert access_index.table_access("fact_sales_lines", role)["readable"] is True


def test_gross_margin_denied_masked_cost_for_marketing(access_index):
    acc = access_index.metric_access("gross_margin", "marketing_ops")
    assert acc["readable"] is False
    assert acc["reason"] == "uses masked column cost_amount"


def test_gross_margin_readable_for_executive(access_index):
    assert access_index.metric_access("gross_margin", "executive")["readable"] is True


def test_inventory_days_denied_table_precedence_for_marketing(access_index):
    # inventory_days reads fact_inventory (unreadable) -> table denial takes precedence.
    acc = access_index.metric_access("inventory_days", "marketing_ops")
    assert acc["readable"] is False
    assert "fact_inventory" in acc["reason"]
    assert "masked" not in acc["reason"]


def test_net_revenue_readable_everywhere(access_index):
    for role in ("executive", "regional_manager", "marketing_ops", "data_analyst"):
        assert access_index.metric_access("net_revenue", role)["readable"] is True


def test_province_dimension_readable_sources_store_not_customer(access_index):
    # province dim sources dim_store.province, which is NOT masked for any role — only
    # dim_customer.province is masked. So the province dimension stays readable.
    for role in ("regional_manager", "marketing_ops", "executive"):
        assert access_index.dimension_access("province", role)["readable"] is True


def test_dimension_denial_on_masked_source_column():
    # A dimension whose source IS a masked column is denied, reason names the column.
    from knowledge_graph.access import AccessIndex

    policy = {"roles": {"r": {"tables": "all", "masked_columns": ["dim_customer.birth_year"]}}}
    semantic = {"dimensions": {"age": {"key": "age", "source": "dim_customer.birth_year"}}, "metrics": {}}
    acc = AccessIndex(policy, semantic).dimension_access("age", "r")
    assert acc["readable"] is False
    assert acc["reason"] == "uses masked column birth_year"


def test_can_compute_excludes_denied(access_index):
    computable = set(access_index.can_compute_metrics("marketing_ops"))
    assert "gross_margin" not in computable
    assert "inventory_days" not in computable
    assert "net_revenue" in computable
    assert "gmv_gross" in computable

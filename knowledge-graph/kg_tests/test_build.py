"""Graph construction + CONTRACT §4.2 invariants against the real vocabulary + snapshot."""

from __future__ import annotations

import copy

import pytest

from knowledge_graph.build import assert_invariants, build_graph


def _labels(graph, label):
    return {n.key for n in graph.nodes if n.label == label}


def _edges(graph, etype):
    return [(e.from_key, e.to_key) for e in graph.edges if e.type == etype]


def test_invariants_hold(graph, semantic):
    assert_invariants(graph, semantic)  # no raise


def test_live_graph_node_and_edge_counts(graph):
    # These counts are built from the LIVE source/semantic/ (no frozen snapshot).
    # When the authored semantic layer changes, these numbers are EXPECTED to move —
    # that is the point of testing against live files. If this assertion fails after a
    # deliberate semantic-layer edit, recount and update it; it is a change detector,
    # not a contract. As of this commit: 54 nodes / 187 edges.
    assert len(graph.nodes) == 54
    assert len(graph.edges) == 187


def test_live_graph_node_counts_by_label(graph):
    from collections import Counter

    counts = Counter(n.label for n in graph.nodes)
    assert counts == {
        "Table": 8,
        "Metric": 10,
        "Dimension": 11,
        "Concept": 13,
        "Constraint": 8,
        "Role": 4,
    }


def test_metric_nodes_match_semantic_layer(graph, semantic):
    # Invariant 3 / success criterion 4: Metric node keys == A's metric keys.
    assert _labels(graph, "Metric") == set(semantic.metrics.keys())


def test_three_parents_have_no_measured_by(graph):
    measured_by_sources = {frm for frm, _ in _edges(graph, "MEASURED_BY")}
    for parent in ("customer-retention", "gmv-revenue", "basket-size"):
        assert parent not in measured_by_sources


def test_variants_each_measure_one_metric(graph):
    mb = _edges(graph, "MEASURED_BY")
    by_src: dict[str, list[str]] = {}
    for src, tgt in mb:
        by_src.setdefault(src, []).append(tgt)
    expected = {
        "repeat-purchase-retention": "repeat_purchase_rate_90d",
        "member-activity-retention": "member_active_rate_30d",
        "gmv-gross": "gmv_gross",
        "net-revenue": "net_revenue",
        "basket-items": "basket_items_avg",
        "basket-value": "basket_value_avg",
    }
    for concept, metric in expected.items():
        assert by_src.get(concept) == [metric]


def test_variant_of_edges_point_to_parents(graph):
    vo = dict(_edges(graph, "VARIANT_OF"))
    assert vo["repeat-purchase-retention"] == "customer-retention"
    assert vo["net-revenue"] == "gmv-revenue"
    assert vo["basket-value"] == "basket-size"


def test_computed_from_excludes_join_only_dims(graph):
    # net_revenue's measures live on fact_sales_lines + fact_returns; dim_store/dim_sku/
    # dim_customer are join-only and must NOT be COMPUTED_FROM targets.
    tables = {t for m, t in _edges(graph, "COMPUTED_FROM") if m == "net_revenue"}
    assert tables == {"fact_sales_lines", "fact_returns"}


def test_can_compute_marketing_ops_excludes_denied(graph):
    cc = {m for r, m in _edges(graph, "CAN_COMPUTE") if r == "marketing_ops"}
    assert "gross_margin" not in cc
    assert "inventory_days" not in cc
    assert "net_revenue" in cc


def test_can_read_marketing_ops_excludes_inventory(graph):
    cr = {t for r, t in _edges(graph, "CAN_READ") if r == "marketing_ops"}
    assert "fact_inventory" not in cr
    assert "fact_sales_lines" in cr


def test_constrains_edges_resolve(graph):
    cons = _edges(graph, "CONSTRAINS")
    assert ("b2b_value_skew", "net_revenue") in cons
    assert ("returns_reduce_gross", "fact_returns") in cons


def test_invariant_violation_detected(graph, semantic):
    # Corrupt a variant to have two MEASURED_BY edges -> invariant 1 must fire.
    from knowledge_graph.build import Edge

    bad = copy.deepcopy(graph)
    bad.edges.append(Edge("MEASURED_BY", "Concept", "net-revenue", "Metric", "gmv_gross"))
    with pytest.raises(AssertionError, match="invariant 1"):
        assert_invariants(bad, semantic)


def test_determinism_same_build_twice(vocabulary, semantic, policy, schema, access_index):
    g1 = build_graph(vocabulary, semantic, policy, schema, access_index)
    g2 = build_graph(vocabulary, semantic, policy, schema, access_index)
    n1 = sorted((n.label, n.key) for n in g1.nodes)
    n2 = sorted((n.label, n.key) for n in g2.nodes)
    e1 = sorted((e.type, e.from_key, e.to_key) for e in g1.edges)
    e2 = sorted((e.type, e.from_key, e.to_key) for e in g2.edges)
    assert n1 == n2
    assert e1 == e2

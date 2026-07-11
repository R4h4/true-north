"""Recursive serialization (CONTRACT §3) produces the CONTRACT §4.1 record shapes.

Structure (key sets, nesting, _access placement) is asserted against the contract
node shapes inline; values are illustrative, so we check shape not content. (These
assertions used to read the replay-stub fixtures as shape oracles; the stub is gone
per ADR 0004, so the expected shapes are pinned here directly.)
"""

from __future__ import annotations

from knowledge_graph.serialize import Serializer

# CONTRACT §4.1 governed-node key sets (Metric/Table/Dimension carry _access on the wire).
_METRIC_KEYS = {"_label", "key", "name", "description", "type", "unit", "formula", "version", "_access"}
_DIMENSION_KEYS = {"_label", "key", "name", "description", "type", "canonical_values", "_access"}
_CONSTRAINT_KEYS = {"_label", "key", "statement", "severity"}
_TABLE_KEYS = {"_label", "key", "description", "grain", "freshness_note", "_access"}


def _shape(obj):
    """Recursively reduce to key sets, dropping scalar values. Homogeneous lists
    reduce to their first element's shape (README: element-shape match, not length)."""
    if isinstance(obj, dict):
        return {k: _shape(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return ["<empty>"] if not obj else [_shape(obj[0])]
    return type(obj).__name__


def test_metric_node_shape_matches_fixture(access_index, fakes):
    ser = Serializer(access_index, "data_analyst")
    node = fakes.Node("Metric", {
        "key": "net_revenue", "name": "Net revenue", "description": "Sales net of returns",
        "type": "derived", "unit": "VND", "formula": "sum(net_amount) - sum(refund_amount)",
        "version": "0.1",
    })
    out = ser.value(node)
    assert set(out.keys()) == _METRIC_KEYS
    assert out["_label"] == "Metric"
    assert out["_access"] == {"readable": True}


def test_denied_metric_carries_reason(access_index, fakes):
    ser = Serializer(access_index, "marketing_ops")
    node = fakes.Node("Metric", {
        "key": "gross_margin", "name": "Gross margin", "description": "…",
        "type": "derived", "unit": "VND", "formula": "…", "version": "0.1",
    })
    out = ser.value(node)
    assert out["_access"]["readable"] is False
    assert out["_access"]["reason"] == "uses masked column cost_amount"


def test_dimension_node_carries_type(access_index, fakes):
    # CONTRACT §4.1 requires Dimension nodes carry `type`. The compiler stamps it
    # (build._dimension_props), and the serializer is a pass-through: whatever props the
    # node has are emitted, plus _access.
    ser = Serializer(access_index, "data_analyst")
    node = fakes.Node("Dimension", {
        "key": "channel", "name": "Sales channel", "description": "…",
        "type": "categorical",
        "canonical_values": ["app", "b2b", "in_store", "web"],
    })
    out = ser.value(node)
    assert out["type"] == "categorical"
    assert set(out.keys()) == {
        "_label", "key", "name", "description", "type", "canonical_values", "_access",
    }


def test_concept_and_constraint_have_no_access(access_index, fakes):
    ser = Serializer(access_index, "marketing_ops")
    concept = fakes.Node("Concept", {"key": "customer-retention", "name": "Customer Retention",
                                   "definition": "…", "aliases": ["retention"]})
    constraint = fakes.Node("Constraint", {"key": "b2b_value_skew", "statement": "…", "severity": "warning"})
    assert "_access" not in ser.value(concept)
    assert "_access" not in ser.value(constraint)


def test_detail_record_shape_matches_contract(access_index, fakes):
    """A full metric-detail record (m + collect(dims/caveats/tables)) matches the
    CONTRACT §4.1 node shapes."""
    ser = Serializer(access_index, "data_analyst")
    m = fakes.Node("Metric", {"key": "net_revenue", "name": "N", "description": "d",
                            "type": "derived", "unit": "VND", "formula": "f", "version": "0.1"})
    d = fakes.Node("Dimension", {"key": "channel", "name": "c", "description": "d",
                              "type": "categorical", "canonical_values": ["app"]})
    k = fakes.Node("Constraint", {"key": "b2b_value_skew", "statement": "s", "severity": "warning"})
    t = fakes.Node("Table", {"key": "fact_sales_lines", "description": "d",
                           "grain": "sales line", "freshness_note": "refreshed daily"})
    record = fakes.Record({"m": m, "dims": [d], "caveats": [k], "tables": [t]})
    out = ser.record(record)
    assert set(out["m"].keys()) == _METRIC_KEYS
    assert set(out["dims"][0].keys()) == _DIMENSION_KEYS
    assert set(out["caveats"][0].keys()) == _CONSTRAINT_KEYS
    assert set(out["tables"][0].keys()) == _TABLE_KEYS


def test_relationship_serialization(access_index, fakes):
    ser = Serializer(access_index, "data_analyst")
    a = fakes.Node("Concept", {"key": "repeat-purchase-retention", "name": "n"})
    b = fakes.Node("Metric", {"key": "repeat_purchase_rate_90d", "name": "n", "description": "d",
                            "type": "ratio", "unit": "ratio", "formula": "f", "version": "0.1"})
    rel = fakes.Rel("MEASURED_BY", a, b)
    out = ser.value(rel)
    assert out["_type"] == "MEASURED_BY"
    assert out["_from"] == "repeat-purchase-retention"
    assert out["_to"] == "repeat_purchase_rate_90d"


def test_path_serialization(access_index, fakes):
    ser = Serializer(access_index, "data_analyst")
    a = fakes.Node("Concept", {"key": "basket-value", "name": "n"})
    b = fakes.Node("Metric", {"key": "basket_value_avg", "name": "n", "description": "d",
                            "type": "ratio", "unit": "VND", "formula": "f", "version": "0.1"})
    rel = fakes.Rel("MEASURED_BY", a, b)
    path = fakes.Path([a, b], [rel])
    out = ser.value(path)
    assert set(out.keys()) == {"nodes", "relationships"}
    assert out["nodes"][1]["_access"] == {"readable": True}
    assert out["relationships"][0]["_type"] == "MEASURED_BY"


def test_scalar_nan_and_dates(access_index, fakes):
    from datetime import date, datetime

    ser = Serializer(access_index, "data_analyst")
    assert ser.value(float("nan")) is None
    assert ser.value(float("inf")) is None
    assert ser.value(date(2025, 12, 21)) == "2025-12-21"
    assert ser.value(datetime(2025, 12, 21, 9, 30, 0)) == "2025-12-21T09:30:00"

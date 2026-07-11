"""Recursive serialization (CONTRACT §3) produces the replay-fixture record shapes.

Structure (key sets, nesting, _access placement) is asserted; values are illustrative
per the golden README, so we check shape not content.
"""

from __future__ import annotations

import json
from pathlib import Path

from knowledge_graph.serialize import Serializer

REPLAY = Path(__file__).resolve().parents[2] / "governance" / "fixtures" / "replay"


def _load_record(fixture: str, idx: int = 0) -> dict:
    data = json.loads((REPLAY / fixture).read_text())
    return data["response"]["result"]["records"][idx]


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
    fixture_m = _load_record("kg-resolve-retention.json")["m"]
    assert set(out.keys()) == set(fixture_m.keys())
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


def test_dimension_node_shape_no_type(access_index, fakes):
    ser = Serializer(access_index, "data_analyst")
    node = fakes.Node("Dimension", {
        "key": "channel", "name": "Sales channel", "description": "…",
        "canonical_values": ["app", "b2b", "in_store", "web"],
    })
    out = ser.value(node)
    fixture_d = _load_record("kg-detail-net-revenue.json")["dims"][0]
    assert set(out.keys()) == set(fixture_d.keys())
    assert "type" not in out  # CONTRACT fixtures omit `type` on Dimension instances


def test_concept_and_constraint_have_no_access(access_index, fakes):
    ser = Serializer(access_index, "marketing_ops")
    concept = fakes.Node("Concept", {"key": "customer-retention", "name": "Customer Retention",
                                   "definition": "…", "aliases": ["retention"]})
    constraint = fakes.Node("Constraint", {"key": "b2b_value_skew", "statement": "…", "severity": "warning"})
    assert "_access" not in ser.value(concept)
    assert "_access" not in ser.value(constraint)


def test_detail_record_shape_matches_fixture(access_index, fakes):
    """A full metric-detail record (m + collect(dims/caveats/tables)) matches shape."""
    ser = Serializer(access_index, "data_analyst")
    m = fakes.Node("Metric", {"key": "net_revenue", "name": "N", "description": "d",
                            "type": "derived", "unit": "VND", "formula": "f", "version": "0.1"})
    d = fakes.Node("Dimension", {"key": "channel", "name": "c", "description": "d",
                              "canonical_values": ["app"]})
    k = fakes.Node("Constraint", {"key": "b2b_value_skew", "statement": "s", "severity": "warning"})
    t = fakes.Node("Table", {"key": "fact_sales_lines", "description": "d",
                           "grain": "sales line", "freshness_note": "refreshed daily"})
    record = fakes.Record({"m": m, "dims": [d], "caveats": [k], "tables": [t]})
    out = ser.record(record)
    fixture = _load_record("kg-detail-net-revenue.json")
    # dims/caveats/tables fixtures have 2+ elements; compare shape of first element.
    assert _shape(out["m"]) == _shape(fixture["m"])
    assert _shape(out["dims"][0]) == _shape(fixture["dims"][0])
    assert _shape(out["caveats"][0]) == _shape(fixture["caveats"][0])
    assert _shape(out["tables"][0]) == _shape(fixture["tables"][0])


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

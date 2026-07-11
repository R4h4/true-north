"""The shared loader exposes authored table semantics (SemanticLayer.tables).

Table semantics (grain, freshness_note, node description) are authored YAML under
source/semantic/tables/*.yml (ADR 0009), parsed by the one shared loader — no
hardcoded map. These tests pin the loader surface the KG compiler reads.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from semantic_layer import Table, load_semantic

REPO_ROOT = Path(__file__).resolve().parents[2]
TABLES_DIR = REPO_ROOT / "source" / "semantic" / "tables"


def test_live_tables_load_as_typed_objects():
    sl = load_semantic()
    assert sl.tables, "expected authored table semantics"
    for key, tbl in sl.tables.items():
        assert isinstance(tbl, Table)
        assert tbl.key == key
        assert tbl.description and tbl.grain and tbl.freshness_note


def test_table_accessor_returns_none_for_unknown():
    sl = load_semantic()
    assert sl.table("nope") is None


def test_every_measure_table_has_semantics():
    sl = load_semantic()
    referenced = {t for m in sl.metrics.values() for t in m.tables}
    assert referenced, "expected metrics referencing tables"
    assert referenced <= set(sl.tables), "every measure table needs a tables/*.yml entry"


def test_values_carried_over_verbatim():
    # fact_inventory's freshness note is the weekly-snapshot trap wording.
    doc = yaml.safe_load((TABLES_DIR / "fact_inventory.yml").read_text())
    sl = load_semantic()
    tbl = sl.table("fact_inventory")
    assert tbl.grain == doc["grain"] == "store × sku × week (snapshot)"
    assert tbl.freshness_note == doc["freshness_note"]

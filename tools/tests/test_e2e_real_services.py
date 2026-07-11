"""End-to-end integration tests against the REAL services (phase-4 gate).

Gated behind TN_E2E=1 — they need generated data (seed 42) in DuckDB and a compiled
Neo4j graph up (docker compose). The conformance suite is the other half of the gate:

    GOVERNED_CLI_CMD="uv run tn" uv run pytest contracts/conformance
    TN_E2E=1 uv run pytest tools/tests/test_e2e_real_services.py

These assert cross-call *invariants* the goldens cannot (goldens are single-call,
structure-only): trap-chain sanity, persona differences, determinism.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TN_E2E"),
    reason="e2e gate: set TN_E2E=1 with data generated and Neo4j up",
)

TN = shlex.split(os.environ.get("GOVERNED_CLI_CMD", "uv run tn"))

MAI = "tok-exec-mai"
DUC = "tok-rm-south-duc"
LAN = "tok-mkt-lan"
BINH = "tok-analyst-binh"
ALL_TOKENS = [MAI, DUC, LAN, BINH]


def tn_raw(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([*TN, *args], capture_output=True, text=True, timeout=120)


def tn(*args: str) -> dict:
    proc = tn_raw(*args)
    envelope = json.loads(proc.stdout)
    assert proc.returncode == (0 if envelope["ok"] else 1)
    return envelope


def total(envelope: dict) -> float:
    """Sum the metric column (last column) across rows."""
    return sum(row[-1] for row in envelope["result"]["rows"] if row[-1] is not None)


def perm_types(envelope: dict) -> set[str]:
    return {p["type"] for p in envelope["metadata"]["applied_permissions"]}


# ---------------------------------------------------------------------------
# Trap-chain sanity invariants
# ---------------------------------------------------------------------------

class TestTrapChainInvariants:
    def test_net_revenue_not_above_gmv_gross(self):
        gross = tn("query", "--token", MAI, "--metric", "gmv_gross")
        net = tn("query", "--token", MAI, "--metric", "net_revenue")
        assert total(net) <= total(gross)
        assert all(isinstance(row[-1], int) for row in gross["result"]["rows"])  # money = int VND

    def test_south_is_a_subset_of_national(self):
        national = tn("query", "--token", MAI, "--metric", "net_revenue", "--group-by", "channel")
        south = tn("query", "--token", DUC, "--metric", "net_revenue", "--group-by", "channel")
        assert total(south) <= total(national)
        assert "row_filter" in perm_types(south)
        assert "row_filter" not in perm_types(national)

    def test_basket_variants_diverge(self):
        # items-vs-value is only a trap if the two variants actually answer differently
        items = tn("query", "--token", BINH, "--metric", "basket_items_avg")
        value = tn("query", "--token", BINH, "--metric", "basket_value_avg")
        assert total(items) != total(value)
        assert items["metadata"]["provenance"]["metric_key"] == "basket_items_avg"

    def test_freshness_as_of_is_min_of_touched_tables(self):
        env = tn("query", "--token", MAI, "--metric", "net_revenue")
        freshness = env["metadata"]["freshness"]
        assert set(freshness) == set(env["metadata"]["provenance"]["tables"])
        assert env["metadata"]["as_of"] == min(freshness.values())

    def test_canonical_value_trap_self_corrects(self):
        env = tn("query", "--token", MAI, "--metric", "net_revenue", "--filter", "channel = 'offline'")
        assert env["error"]["code"] == "INVALID_DIMENSION_VALUE"
        assert env["error"]["details"]["did_you_mean"] == "in_store"


# ---------------------------------------------------------------------------
# Persona matrix — same catalog, four different worlds
# ---------------------------------------------------------------------------

class TestPersonaMatrix:
    def test_metrics_list_never_hides_only_annotates(self):
        keys_by_token = {}
        for token in ALL_TOKENS:
            env = tn("metrics", "list", "--token", token)
            keys_by_token[token] = {m["key"]: m["access"]["allowed"] for m in env["result"]["metrics"]}
        # same catalog for everyone (annotate, don't hide) ...
        assert len({frozenset(k) for k in keys_by_token.values()}) == 1
        # ... but lan cannot compute margin/inventory while mai and binh can
        assert keys_by_token[LAN]["gross_margin"] is False
        assert keys_by_token[LAN]["inventory_days"] is False
        assert keys_by_token[MAI]["gross_margin"] is True
        assert keys_by_token[BINH]["gross_margin"] is True

    def test_denial_precedence(self):
        masked = tn("query", "--token", LAN, "--metric", "gross_margin")
        assert masked["error"]["code"] == "ACCESS_DENIED_METRIC"
        assert "cost" in masked["error"]["details"]["reason"]
        table = tn("query", "--token", LAN, "--metric", "inventory_days")
        assert table["error"]["code"] == "ACCESS_DENIED_TABLE"
        assert table["error"]["details"]["table"] == "fact_inventory"

    def test_masked_values_never_appear(self):
        # duc: dim_customer.province is masked -> the backing dimension is denied outright
        env = tn("dimensions", "list", "--token", DUC)
        denied = [d for d in env["result"]["dimensions"] if not d["access"]["allowed"]]
        assert any(d.get("source") == "dim_customer.province" for d in denied)

    def test_tokenization_disclosed_and_stable(self):
        env = tn("whoami", "--token", BINH)
        assert any(p["type"] == "column_tokenized" for p in env["result"]["permissions"])

    def test_kg_access_annotations_per_persona(self):
        cypher = (
            "MATCH (m:Metric) WHERE m.key IN ['net_revenue','gross_margin'] "
            "OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) RETURN m, collect(k) AS caveats"
        )
        env = tn("kg", "query", "--token", LAN, cypher)
        access = {
            record["m"]["key"]: record["m"]["_access"] for record in env["result"]["records"]
        }
        assert access["net_revenue"]["readable"] is True
        assert access["gross_margin"]["readable"] is False
        assert access["gross_margin"]["reason"]

    def test_kg_denials_are_never_silently_undisclosed(self):
        # The disclosure promise, pinned as an invariant instead of golden shapes:
        # every masked-column denial visible in a response's _access annotations
        # must be explained by a column_masked/column_banded object in that same
        # response's applied_permissions. Guards _kg_touched_tables against
        # unrecognized record shapes silently yielding an empty disclosure.
        queries = [
            "MATCH (m:Metric) RETURN m",
            "MATCH (d:Dimension) RETURN d",
            "MATCH (m:Metric)-[:COMPUTED_FROM]->(t:Table) RETURN m, collect(t) AS tables",
            "MATCH (c:Concept)-[:MEASURED_BY]->(m:Metric) RETURN c, {metric: m} AS wrapped",
        ]
        for token in (MAI, DUC, LAN, BINH):
            for cypher in queries:
                env = tn("kg", "query", "--token", token, cypher)
                disclosed = {
                    p["column"].split(".", 1)[1]
                    for p in env["metadata"]["applied_permissions"]
                    if p["type"] in ("column_masked", "column_banded")
                }

                def walk(v):
                    if isinstance(v, dict):
                        acc = v.get("_access")
                        if acc and not acc["readable"] and "masked column" in acc.get("reason", ""):
                            col = acc["reason"].rsplit(" ", 1)[-1].split(".")[-1]
                            assert col in disclosed, (
                                f"{token} {cypher!r}: denial on {v.get('key')} names masked "
                                f"column '{col}' but applied_permissions discloses {disclosed}"
                            )
                        for x in v.values():
                            walk(x)
                    elif isinstance(v, list):
                        for x in v:
                            walk(x)

                walk(env["result"]["records"])


# ---------------------------------------------------------------------------
# Graph invariants through the real compile
# ---------------------------------------------------------------------------

class TestGraphInvariants:
    def test_parents_have_no_measured_by_and_variants_exactly_one(self):
        env = tn(
            "kg", "query", "--token", BINH,
            "MATCH (p:Concept)<-[:VARIANT_OF]-(v:Concept) "
            "OPTIONAL MATCH (p)-[:MEASURED_BY]->(pm:Metric) "
            "OPTIONAL MATCH (v)-[:MEASURED_BY]->(vm:Metric) "
            "RETURN p.key AS parent, pm.key AS parent_metric, v.key AS variant, vm.key AS variant_metric",
        )
        records = env["result"]["records"]
        assert records, "expected at least the three planted variant families"
        assert all(r["parent_metric"] is None for r in records)
        assert all(r["variant_metric"] is not None for r in records)

    def test_metric_nodes_mirror_metrics_list(self):
        graph = tn("kg", "query", "--token", MAI, "MATCH (m:Metric) RETURN m.key AS key ORDER BY key")
        catalog = tn("metrics", "list", "--token", MAI)
        graph_keys = sorted(r["key"] for r in graph["result"]["records"])
        catalog_keys = sorted(m["key"] for m in catalog["result"]["metrics"])
        assert graph_keys == catalog_keys

    def test_writes_rejected(self):
        env = tn("kg", "query", "--token", BINH, "CREATE (m:Metric {key: 'fake'}) RETURN m")
        assert env["error"]["code"] == "QUERY_REJECTED"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_identical_query_identical_envelope(self):
        args = ("query", "--token", DUC, "--metric", "net_revenue", "--group-by", "channel")
        first, second = tn_raw(*args), tn_raw(*args)
        assert first.stdout == second.stdout

    def test_compiled_sql_is_stable(self):
        args = ("query", "--token", MAI, "--metric", "gmv_gross", "--group-by", "channel")
        one = tn(*args)["metadata"]["provenance"]["compiled_sql"]
        two = tn(*args)["metadata"]["provenance"]["compiled_sql"]
        assert one == two

"""Fixture entry gate (phase-3 step 3): replay every CLI invocation the four
DoD conversations need and assert the stub answers with the expected outcome.

Run from repo root:  uv run python harness/scripts/check_fixtures.py
Exit 0 = gate open. KNOWN GAPS are asserted too (they currently return
INTERNAL "no replay fixture") so this script doubles as the checklist for
fixture-only PRs; when Karsten adds a fixture the gap line flips to FIXED and
should be promoted to the main list.
"""

import sys

sys.path.insert(0, "harness")

from agent.tn_client import run_tn  # noqa: E402
from agent.tools import resolve_term_cypher  # noqa: E402

METRIC_DETAIL = (
    "MATCH (m:Metric {{key: '{key}'}}) "
    "OPTIONAL MATCH (m)-[:HAS_DIMENSION]->(d:Dimension) "
    "OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) "
    "OPTIONAL MATCH (m)-[:COMPUTED_FROM]->(t:Table) "
    "RETURN m, collect(DISTINCT d) AS dims, collect(DISTINCT k) AS caveats, "
    "collect(DISTINCT t) AS tables"
)
ACCESS_LAN = (
    "MATCH (m:Metric) WHERE m.key IN ['net_revenue','gross_margin'] "
    "OPTIONAL MATCH (k:Constraint)-[:CONSTRAINS]->(m) "
    "RETURN m, collect(k) AS caveats"
)

BINH, MAI, DUC, LAN = "tok-analyst-binh", "tok-exec-mai", "tok-rm-south-duc", "tok-mkt-lan"

# (label, args, expected error.code or None for success)
CHECKS = [
    # Bootstrap
    ("kg schema", ["kg", "schema"], None),
    ("whoami binh", ["whoami", "--token", BINH], None),
    ("metrics list mai", ["metrics", "list", "--token", MAI], None),
    # DoD-1: Binh, retention ambiguity -> variant -> chart
    ("DoD1 resolve retention", ["kg", "query", resolve_term_cypher("retention"), "--token", BINH], None),
    ("DoD1 metric detail", ["kg", "query", METRIC_DETAIL.format(key="repeat_purchase_rate_90d"), "--token", BINH], None),
    ("DoD1 query", ["query", "--metric", "repeat_purchase_rate_90d", "--group-by", "channel", "--token", BINH], None),
    # DoD-2: Mai vs Duc row filter
    ("DoD2 resolve revenue (mai)", ["kg", "query", resolve_term_cypher("revenue|gmv"), "--token", MAI], None),
    ("DoD2 detail net_revenue (mai)", ["kg", "query", METRIC_DETAIL.format(key="net_revenue"), "--token", MAI], None),
    ("DoD2 query mai", ["query", "--metric", "net_revenue", "--group-by", "channel", "--token", MAI], None),
    ("DoD2 query duc", ["query", "--metric", "net_revenue", "--group-by", "channel", "--token", DUC], None),
    # DoD-3: Lan exists-but-denied
    ("DoD3 access annotations (lan)", ["kg", "query", ACCESS_LAN, "--token", LAN], None),
    ("DoD3 describe gross_margin (lan)", ["metrics", "describe", "gross_margin", "--token", LAN], None),
    ("DoD3 gross_margin denied", ["query", "--metric", "gross_margin", "--group-by", "category", "--token", LAN], "ACCESS_DENIED_METRIC"),
    ("DoD3 inventory_days denied", ["query", "--metric", "inventory_days", "--token", LAN], "ACCESS_DENIED_TABLE"),
    # DoD-4: Mai self-correction
    ("DoD4 metric not found", ["query", "--metric", "revenue", "--token", MAI], "METRIC_NOT_FOUND"),
    ("DoD4 bad dim value", ["query", "--metric", "net_revenue", "--filter", "channel = 'offline'", "--token", MAI], "INVALID_DIMENSION_VALUE"),
]

# Requests the DoD conversations will realistically make that have NO fixture
# yet -> each needs a fixture-only PR. Asserted as INTERNAL so drift is loud.
KNOWN_GAPS = [
    ("GAP DoD4 corrected retry (in_store)", ["query", "--metric", "net_revenue", "--group-by", "channel", "--filter", "channel = 'in_store'", "--token", MAI]),
    ("GAP DoD2 duc resolve revenue", ["kg", "query", resolve_term_cypher("revenue|gmv"), "--token", DUC]),
    ("GAP DoD3 lan resolve margin", ["kg", "query", resolve_term_cypher("margin"), "--token", LAN]),
]


def main() -> int:
    failures = 0
    for label, args, expected_error in CHECKS:
        env = run_tn(args)
        code = (env.get("error") or {}).get("code")
        ok = code == expected_error if expected_error else env.get("ok") is True
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got error={code})"))
        failures += 0 if ok else 1

    for label, args in KNOWN_GAPS:
        env = run_tn(args)
        code = (env.get("error") or {}).get("code")
        if code == "INTERNAL":
            print(f"GAP   {label}  (needs fixture-only PR)")
        else:
            print(f"FIXED {label}  (fixture landed - promote to CHECKS)")

    print(f"\n{'GATE OPEN' if failures == 0 else 'GATE CLOSED'}: {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

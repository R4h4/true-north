"""Governed-CLI entry gate: run every CLI invocation the four DoD
conversations need against the live `tn` CLI and assert the expected outcome.

Prereqs (see docs/USING-TN.md): Neo4j up (`docker compose up -d`), data
generated, graph compiled. Run from repo root:
    uv run python harness/scripts/check_fixtures.py
Exit 0 = gate open.
"""

import sys

sys.path.insert(0, "harness")

from agent.tn_client import run_tn  # noqa: E402
from agent.tools import (  # noqa: E402
    access_check_cypher,
    metric_detail_cypher,
    resolve_term_cypher,
)

# The gate exercises the SAME Cypher renderers the live tools use - if a
# template drifts from what the graph answers, the gate fails loudly here
# instead of the agent failing mid-demo.

BINH, MAI, DUC, LAN = "tok-analyst-binh", "tok-exec-mai", "tok-rm-south-duc", "tok-mkt-lan"

# (label, args, expected error.code or None for success)
CHECKS = [
    # Bootstrap
    ("kg schema", ["kg", "schema"], None),
    ("whoami binh", ["whoami", "--token", BINH], None),
    ("metrics list mai", ["metrics", "list", "--token", MAI], None),
    # DoD-1: Binh, retention ambiguity -> variant -> chart
    ("DoD1 resolve retention", ["kg", "query", resolve_term_cypher("retention"), "--token", BINH], None),
    ("DoD1 metric detail", ["kg", "query", metric_detail_cypher("repeat_purchase_rate_90d"), "--token", BINH], None),
    ("DoD1 query", ["query", "--metric", "repeat_purchase_rate_90d", "--group-by", "channel", "--token", BINH], None),
    # DoD-2: Mai vs Duc row filter
    ("DoD2 resolve revenue (mai)", ["kg", "query", resolve_term_cypher("revenue|gmv"), "--token", MAI], None),
    ("DoD2 resolve revenue (duc)", ["kg", "query", resolve_term_cypher("revenue|gmv"), "--token", DUC], None),
    ("DoD2 detail net_revenue (mai)", ["kg", "query", metric_detail_cypher("net_revenue"), "--token", MAI], None),
    ("DoD2 query mai", ["query", "--metric", "net_revenue", "--group-by", "channel", "--token", MAI], None),
    ("DoD2 query duc", ["query", "--metric", "net_revenue", "--group-by", "channel", "--token", DUC], None),
    # DoD-3: Lan exists-but-denied
    ("DoD3 resolve margin (lan)", ["kg", "query", resolve_term_cypher("margin"), "--token", LAN], None),
    ("DoD3 access annotations (lan)", ["kg", "query", access_check_cypher(['net_revenue','gross_margin']), "--token", LAN], None),
    ("DoD3 describe gross_margin (lan)", ["metrics", "describe", "gross_margin", "--token", LAN], None),
    ("DoD3 gross_margin denied", ["query", "--metric", "gross_margin", "--group-by", "category", "--token", LAN], "ACCESS_DENIED_METRIC"),
    ("DoD3 inventory_days denied", ["query", "--metric", "inventory_days", "--token", LAN], "ACCESS_DENIED_TABLE"),
    # DoD-4: Mai self-correction
    ("DoD4 metric not found", ["query", "--metric", "revenue", "--token", MAI], "METRIC_NOT_FOUND"),
    ("DoD4 bad dim value", ["query", "--metric", "net_revenue", "--filter", "channel = 'offline'", "--token", MAI], "INVALID_DIMENSION_VALUE"),
    ("DoD4 corrected retry (in_store)", ["query", "--metric", "net_revenue", "--group-by", "channel", "--filter", "channel = 'in_store'", "--token", MAI], None),
]


def main() -> int:
    failures = 0
    for label, args, expected_error in CHECKS:
        env = run_tn(args)
        code = (env.get("error") or {}).get("code")
        ok = code == expected_error if expected_error else env.get("ok") is True
        print(f"{'PASS' if ok else 'FAIL'}  {label}" + ("" if ok else f"  (got error={code})"))
        failures += 0 if ok else 1

    print(f"\n{'GATE OPEN' if failures == 0 else 'GATE CLOSED'}: {failures} failures")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

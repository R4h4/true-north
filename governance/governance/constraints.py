"""Constraint-key adapter (integration seam for Agent B's vocabulary).

provenance.constraint_keys lists the constraints attached to a metric's
tables/metrics — keys only. The authored constraints live in
knowledge-graph/vocabulary/constraints/*.yml, which is NOT on this branch (Agent
B lands it, the coordinator merges). Until then this scans that dir at runtime
and returns [] when absent, so the field is present and empty and lights up once
the vocabulary merges — no code change needed then.

# integration: knowledge-graph/vocabulary/constraints/ is owned by Agent B.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONSTRAINTS_DIR = REPO_ROOT / "knowledge-graph" / "vocabulary" / "constraints"


@lru_cache(maxsize=None)
def _load_constraints(constraints_dir: Path = CONSTRAINTS_DIR) -> tuple[dict, ...]:
    if not constraints_dir.is_dir():
        return ()
    out: list[dict] = []
    for path in sorted(constraints_dir.glob("*.yml")):
        try:
            doc = yaml.safe_load(path.read_text())
        except Exception:
            continue
        if isinstance(doc, dict) and "key" in doc:
            out.append(doc)
    return tuple(out)


def constraint_keys_for(
    metric_key: str, tables: list[str], constraints_dir: Path = CONSTRAINTS_DIR
) -> list[str]:
    """Keys of constraints whose `constrains` targets this metric or a touched
    table. Deterministic order (sorted). The dir is the DATASET's vocabulary
    constraints folder (retail default == the historical hard-coded path)."""
    keys: set[str] = set()
    targets = {f"metric:{metric_key}"} | {f"table:{t}" for t in tables}
    for c in _load_constraints(constraints_dir):
        for tgt in c.get("constrains") or []:
            if tgt in targets:
                keys.add(c["key"])
    return sorted(keys)

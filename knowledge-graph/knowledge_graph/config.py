"""Connection + path config for the knowledge-graph service.

Bolt credentials default to the docker-compose dev values (docker-compose.yml);
override via env for CI or an alternate instance. Repo paths resolve the source
of truth locations the compiler reads.
"""

from __future__ import annotations

import os
from pathlib import Path

from semantic_layer.datasets import Dataset, get_dataset

# knowledge-graph/knowledge_graph/config.py -> repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]

# Module-level constants are the retail defaults, preserved for any caller that
# imports them directly. Dataset-aware paths resolve through the registry via
# resolve_paths()/bolt_uri(dataset=...); everything without a dataset stays retail.
VOCAB_DIR = REPO_ROOT / "knowledge-graph" / "vocabulary"
SEMANTIC_DIR = REPO_ROOT / "source" / "semantic"
USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"
SCHEMA_PY = REPO_ROOT / "source" / "generator" / "schema.py"

# Business-local timezone for the graph_compiled_at stamp (CONTRACT §2: TIMESTAMP
# is business-local, Asia/Ho_Chi_Minh, no offset suffix).
BUSINESS_TZ = "Asia/Ho_Chi_Minh"


def resolve_dataset(dataset: str | Dataset | None = None) -> Dataset:
    """Accept a key, a Dataset, or None (-> TN_DATASET/retail)."""
    if isinstance(dataset, Dataset):
        return dataset
    return get_dataset(dataset)


def bolt_uri(dataset: str | Dataset | None = None) -> str:
    """Bolt URI for the dataset's Neo4j instance.

    retail keeps today's resolution (NEO4J_BOLT_URI or 7687); a non-default
    dataset reads its own override env var and falls back to its own port.
    """
    return resolve_dataset(dataset).bolt_uri()


def bolt_auth() -> tuple[str, str]:
    # Same fixed dev credentials across instances (non-goal: real per-tenant auth).
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "true-north-dev")
    return user, password

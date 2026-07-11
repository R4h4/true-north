"""Connection + path config for the knowledge-graph service.

Bolt credentials default to the docker-compose dev values (docker-compose.yml);
override via env for CI or an alternate instance. Repo paths resolve the source
of truth locations the compiler reads.
"""

from __future__ import annotations

import os
from pathlib import Path

# knowledge-graph/knowledge_graph/config.py -> repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]

VOCAB_DIR = REPO_ROOT / "knowledge-graph" / "vocabulary"
SEMANTIC_DIR = REPO_ROOT / "source" / "semantic"
USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"
SCHEMA_PY = REPO_ROOT / "source" / "generator" / "schema.py"

# Business-local timezone for the graph_compiled_at stamp (CONTRACT §2: TIMESTAMP
# is business-local, Asia/Ho_Chi_Minh, no offset suffix).
BUSINESS_TZ = "Asia/Ho_Chi_Minh"


def bolt_uri() -> str:
    return os.environ.get("NEO4J_BOLT_URI", "bolt://localhost:7687")


def bolt_auth() -> tuple[str, str]:
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "true-north-dev")
    return user, password

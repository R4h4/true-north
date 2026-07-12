"""Dataset registry — the ONE seam for multi-dataset (multi-tenant) support (ADR 0011).

A dataset is a self-contained bundle of paths and scopes. Everything that today
hard-codes a retail path — the warehouse data dir, the semantic YAML dir,
schema.py, the KG vocabulary, users.yaml, the Neo4j bolt URI, the Postgres
schema — resolves through here instead. ``retail`` is the default and maps to
the EXACT current paths (no file moves, no behavior change); ``shinhan`` maps to
a self-contained bundle under ``source/datasets/shinhan/`` whose files land on a
parallel branch.

Registry entries are pure path math: constructing a Dataset (or resolving one)
must NOT require any of its files to exist. Isolation is per instance/schema:
Neo4j is instance-per-dataset (arbitrary Cypher can't be tenant-scoped
reliably), Postgres is schema-per-dataset (retail == ``public`` for zero churn).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# source/semantic_layer/datasets.py -> the repo root is three parents up.
REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_KEY = "retail"


class UnknownDataset(Exception):
    """Raised when a dataset key is not registered. Names the valid keys."""

    def __init__(self, key: str) -> None:
        valid = ", ".join(sorted(_REGISTRY))
        super().__init__(f"unknown dataset '{key}'; valid datasets: {valid}")
        self.key = key


@dataclass(frozen=True)
class Dataset:
    """A dataset's bundle of paths + isolation scopes.

    ``bolt_env`` / ``bolt_default`` drive ``bolt_uri()``: retail keeps today's
    resolution (``NEO4J_BOLT_URI`` or 7687); a non-default dataset reads its own
    override env var and falls back to its own port so the instances never
    collide.
    """

    key: str
    data_dir: Path
    semantic_dir: Path
    schema_py: Path
    vocab_dir: Path
    users_yaml: Path
    pg_schema: str
    bolt_env: str
    bolt_default: str

    def bolt_uri(self) -> str:
        return os.environ.get(self.bolt_env) or self.bolt_default


def _retail() -> Dataset:
    return Dataset(
        key="retail",
        data_dir=REPO_ROOT / "source" / "data",
        semantic_dir=REPO_ROOT / "source" / "semantic",
        schema_py=REPO_ROOT / "source" / "generator" / "schema.py",
        vocab_dir=REPO_ROOT / "knowledge-graph" / "vocabulary",
        users_yaml=REPO_ROOT / "governance" / "fixtures" / "users.yaml",
        pg_schema="public",
        bolt_env="NEO4J_BOLT_URI",
        bolt_default="bolt://localhost:7687",
    )


def _shinhan() -> Dataset:
    root = REPO_ROOT / "source" / "datasets" / "shinhan"
    return Dataset(
        key="shinhan",
        data_dir=root / "data",
        semantic_dir=root / "semantic",
        schema_py=root / "generator" / "schema.py",
        vocab_dir=root / "vocabulary",
        users_yaml=root / "users.yaml",
        pg_schema="tn_shinhan",
        bolt_env="NEO4J_BOLT_URI_SHINHAN",
        bolt_default="bolt://localhost:7688",
    )


_REGISTRY: dict[str, Dataset] = {
    "retail": _retail(),
    "shinhan": _shinhan(),
}


def all_datasets() -> tuple[Dataset, ...]:
    """Every registered dataset, in registry order (for whole-registry sweeps
    like tools.validate — anything less re-creates the retail-only blind spot)."""
    return tuple(_REGISTRY.values())


def get_dataset(key: str | None = None) -> Dataset:
    """Resolve a Dataset. Precedence: explicit ``key`` > ``TN_DATASET`` env > retail.

    Raises ``UnknownDataset`` (naming the valid keys) for an unregistered key.
    """
    resolved = key or os.environ.get("TN_DATASET") or DEFAULT_KEY
    try:
        return _REGISTRY[resolved]
    except KeyError:
        raise UnknownDataset(resolved) from None

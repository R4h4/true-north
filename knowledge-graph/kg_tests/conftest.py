"""Shared fixtures for KG unit tests — no running Neo4j required.

The graph is built from the authored vocabulary + a FROZEN SNAPSHOT of Agent A's
semantic layer (tests/fixtures/semantic/, see SNAPSHOT.txt) so unit tests are stable
regardless of A's live branch. Fake node/relationship/path objects duck-type the neo4j
driver's graph types for serialization tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_graph import config
from knowledge_graph.access import AccessIndex
from knowledge_graph.build import build_graph
from knowledge_graph.loaders import (
    load_policy,
    load_schema,
    load_semantic,
    load_vocabulary,
)

REPO_ROOT = config.REPO_ROOT
SNAPSHOT_SEMANTIC = Path(__file__).parent / "fixtures" / "semantic"


@pytest.fixture(scope="session")
def vocabulary() -> dict:
    return load_vocabulary(config.VOCAB_DIR)


@pytest.fixture(scope="session")
def semantic() -> dict:
    return load_semantic(SNAPSHOT_SEMANTIC)


@pytest.fixture(scope="session")
def policy() -> dict:
    return load_policy(config.USERS_YAML)


@pytest.fixture(scope="session")
def schema():
    return load_schema(config.SCHEMA_PY)


@pytest.fixture(scope="session")
def access_index(policy, semantic) -> AccessIndex:
    return AccessIndex(policy, semantic)


@pytest.fixture(scope="session")
def graph(vocabulary, semantic, policy, schema, access_index):
    return build_graph(vocabulary, semantic, policy, schema, access_index)


# --- fake neo4j graph entities (duck-typed) -------------------------------

class FakeNode:
    def __init__(self, label: str, props: dict) -> None:
        self.labels = frozenset({label})
        self._props = dict(props)

    def __iter__(self):
        return iter(self._props)

    def items(self):
        return self._props.items()

    def __getitem__(self, k):
        return self._props[k]

    def keys(self):
        return self._props.keys()


class FakeRel:
    def __init__(self, rel_type: str, start: FakeNode, end: FakeNode, props: dict | None = None) -> None:
        self.type = rel_type
        self.start_node = start
        self.end_node = end
        self._props = dict(props or {})

    def items(self):
        return self._props.items()

    def __iter__(self):
        return iter(self._props)

    def keys(self):
        return self._props.keys()

    def __getitem__(self, k):
        return self._props[k]


class FakePath:
    def __init__(self, nodes: list[FakeNode], relationships: list[FakeRel]) -> None:
        self.nodes = nodes
        self.relationships = relationships


class FakeRecord:
    def __init__(self, mapping: dict) -> None:
        self._mapping = dict(mapping)

    def items(self):
        return self._mapping.items()


class _Fakes:
    Node = FakeNode
    Rel = FakeRel
    Path = FakePath
    Record = FakeRecord


@pytest.fixture(scope="session")
def fakes():
    """Duck-typed neo4j graph entity constructors, provided as a fixture so tests need
    no cross-package import (the tests dir is intentionally not a package — its name
    would collide with governance/tests)."""
    return _Fakes

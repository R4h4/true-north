"""Compile the knowledge graph into Neo4j — full wipe-and-rebuild.

    uv run python -m knowledge_graph.compile

Reads the three sources of truth (vocabulary, semantic layer, policy) + schema.py,
builds the node/edge set (build.py), asserts the CONTRACT §4.2 invariants, then wipes
and rewrites the graph in one transaction stamped with `graph_compiled_at` (ISO,
Asia/Ho_Chi_Minh). Idempotent: two consecutive compiles produce identical graphs
(the stamp excepted).

The stamp is written to a singleton (:GraphMeta) node; the API reads it back so every
`tn kg query`/`schema` response can carry `graph_compiled_at`.
"""

from __future__ import annotations

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from knowledge_graph import config
from knowledge_graph.access import AccessIndex
from knowledge_graph.build import Graph, assert_invariants, build_graph
from knowledge_graph.loaders import (
    load_policy,
    load_schema,
    load_semantic,
    load_vocabulary,
)


def build_from_sources() -> tuple[Graph, dict, AccessIndex]:
    """Load sources, build the graph, assert invariants. No Neo4j needed."""
    vocabulary = load_vocabulary(config.VOCAB_DIR)
    semantic = load_semantic(config.SEMANTIC_DIR)
    policy = load_policy(config.USERS_YAML)
    schema = load_schema(config.SCHEMA_PY)
    access_index = AccessIndex(policy, semantic)

    graph = build_graph(vocabulary, semantic, policy, schema, access_index)
    assert_invariants(graph, semantic)
    return graph, semantic, access_index


def _compiled_at() -> str:
    return datetime.now(ZoneInfo(config.BUSINESS_TZ)).strftime("%Y-%m-%dT%H:%M:%S")


def write_graph(graph: Graph, compiled_at: str) -> None:
    """Wipe and rewrite Neo4j in one transaction."""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(config.bolt_uri(), auth=config.bolt_auth())
    try:
        with driver.session() as session:
            session.execute_write(_write_tx, graph, compiled_at)
    finally:
        driver.close()


def _write_tx(tx, graph: Graph, compiled_at: str) -> None:
    tx.run("MATCH (n) DETACH DELETE n")

    # Nodes, grouped by label so the label is a literal (Cypher can't parameterize labels).
    by_label: dict[str, list[dict]] = {}
    for n in graph.nodes:
        by_label.setdefault(n.label, []).append(n.props)
    for label, rows in by_label.items():
        tx.run(f"UNWIND $rows AS p CREATE (n:{label}) SET n = p", rows=rows)

    # Edges, grouped by (type, from_label, to_label) — all literals in the pattern.
    by_type: dict[tuple[str, str, str], list[dict]] = {}
    for e in graph.edges:
        by_type.setdefault((e.type, e.from_label, e.to_label), []).append(
            {"from": e.from_key, "to": e.to_key}
        )
    for (etype, flabel, tlabel), rows in by_type.items():
        tx.run(
            f"UNWIND $rows AS r "
            f"MATCH (a:{flabel} {{key: r.from}}), (b:{tlabel} {{key: r.to}}) "
            f"CREATE (a)-[:{etype}]->(b)",
            rows=rows,
        )

    tx.run(
        "CREATE (m:GraphMeta {key: 'graph_meta', graph_compiled_at: $compiled_at})",
        compiled_at=compiled_at,
    )


def main() -> int:
    graph, _semantic, _access = build_from_sources()
    compiled_at = _compiled_at()
    print(
        f"built graph: {len(graph.nodes)} nodes, {len(graph.edges)} edges; invariants ok",
        file=sys.stderr,
    )
    write_graph(graph, compiled_at)
    print(f"wrote graph to {config.bolt_uri()} @ {compiled_at}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

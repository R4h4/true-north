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

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from governance.policy import load_policy as load_governance_policy
from semantic_layer.datasets import Dataset, get_dataset

from knowledge_graph import config
from knowledge_graph.access import AccessIndex
from knowledge_graph.build import Graph, assert_invariants, build_graph
from knowledge_graph.loaders import (
    load_policy,
    load_schema,
    load_semantic,
    load_vocabulary,
)


def build_from_sources(dataset: Dataset | None = None) -> tuple[Graph, object, AccessIndex]:
    """Load the dataset's sources, build the graph, assert invariants. No Neo4j needed.

    Defaults to retail (TN_DATASET/registry) so existing no-arg callers are
    unchanged; a non-default dataset reads its own bundle of paths.
    """
    ds = dataset or get_dataset()
    vocabulary = load_vocabulary(ds.vocab_dir)
    semantic = load_semantic(ds.semantic_dir)
    policy = load_policy(ds.users_yaml)  # raw dict: Role nodes in build_graph
    schema = load_schema(ds.schema_py)
    # Access derivation is single-sourced in governance.policy; the KG access index is a
    # thin adapter over it (ADR 0009).
    gpolicy = load_governance_policy(ds.users_yaml, semantic=semantic, dataset=ds.key)
    access_index = AccessIndex(gpolicy)

    graph = build_graph(vocabulary, semantic, policy, schema, access_index)
    assert_invariants(graph, semantic)
    return graph, semantic, access_index


def _compiled_at() -> str:
    return datetime.now(ZoneInfo(config.BUSINESS_TZ)).strftime("%Y-%m-%dT%H:%M:%S")


def write_graph(graph: Graph, compiled_at: str, dataset: Dataset | None = None) -> None:
    """Wipe and rewrite the dataset's Neo4j instance in one transaction.

    The full-wipe DETACH DELETE is safe because isolation is per instance: each
    dataset has its own Neo4j (retail 7687, shinhan 7688), so wiping one never
    touches another's graph."""
    from neo4j import GraphDatabase

    ds = dataset or get_dataset()
    driver = GraphDatabase.driver(config.bolt_uri(ds), auth=config.bolt_auth())
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compile the knowledge graph into Neo4j.")
    parser.add_argument(
        "--dataset",
        default=None,
        help="dataset key (default: TN_DATASET env or 'retail'); reads that "
        "bundle and writes to that dataset's Neo4j instance",
    )
    args = parser.parse_args(argv)
    ds = get_dataset(args.dataset)

    graph, _semantic, _access = build_from_sources(ds)
    compiled_at = _compiled_at()
    print(
        f"built graph [{ds.key}]: {len(graph.nodes)} nodes, {len(graph.edges)} edges; invariants ok",
        file=sys.stderr,
    )
    write_graph(graph, compiled_at, ds)
    print(f"wrote graph to {config.bolt_uri(ds)} @ {compiled_at}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

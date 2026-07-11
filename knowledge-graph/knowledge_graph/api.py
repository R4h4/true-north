"""Graph API consumed by the governed CLI at integration.

The CLI wires `tn kg schema` -> get_schema() and `tn kg query` -> run_cypher(); it owns
token->role resolution, the outer envelope, applied_permissions, and mapping the typed
exceptions here to error codes. This module owns: the schema payload, read-only Cypher
execution, and recursive per-role serialization with `_access` (CONTRACT §3).

    from knowledge_graph.api import get_schema, run_cypher
    get_schema() -> dict                       # kg schema result
    run_cypher(cypher, role) -> dict           # {records: [...], graph_compiled_at: ...}

Raises knowledge_graph.errors.QueryRejected (-> QUERY_REJECTED) and InvalidQuery
(-> INVALID_QUERY). The AccessIndex is derived from the same sources as the compiler, so
`_access` is consistent with the compiled CAN_READ/CAN_COMPUTE edges.
"""

from __future__ import annotations

from governance.policy import load_policy as load_governance_policy
from semantic_layer.datasets import Dataset, get_dataset

from knowledge_graph import config
from knowledge_graph.access import AccessIndex
from knowledge_graph.errors import InvalidQuery
from knowledge_graph.loaders import load_semantic
from knowledge_graph.readonly import check_read_only
from knowledge_graph.schema_doc import schema_result
from knowledge_graph.serialize import Serializer


def get_schema() -> dict:
    """Static self-description of the graph (no token, no DB round-trip)."""
    return schema_result()


def _access_index(dataset: Dataset | None = None) -> AccessIndex:
    ds = dataset or get_dataset()
    semantic = load_semantic(ds.semantic_dir)
    policy = load_governance_policy(ds.users_yaml, semantic=semantic, dataset=ds.key)
    return AccessIndex(policy)


def _driver(dataset: Dataset | None = None):
    from neo4j import GraphDatabase

    return GraphDatabase.driver(config.bolt_uri(dataset), auth=config.bolt_auth())


def _graph_compiled_at(session) -> str | None:
    rec = session.run(
        "MATCH (m:GraphMeta {key: 'graph_meta'}) RETURN m.graph_compiled_at AS ts"
    ).single()
    return rec["ts"] if rec else None


def compiled_at(dataset: Dataset | None = None) -> str | None:
    """Best-effort compile stamp for surfaces that don't run a query (kg schema).

    Returns None when the graph is unreachable rather than raising — the schema
    payload itself is static and must not require a live DB.
    """
    try:
        driver = _driver(dataset)
        try:
            with driver.session() as session:
                return _graph_compiled_at(session)
        finally:
            driver.close()
    except Exception:
        return None


def run_cypher(
    cypher: str, role: str, *,
    access_index: AccessIndex | None = None,
    dataset: Dataset | None = None,
) -> dict:
    """Execute read-only Cypher for `role`, returning serialized records + the compile stamp.

    - Rejects writes/multi-statement via the pre-check (QueryRejected).
    - Runs in a bolt READ session; syntax errors surface as InvalidQuery.
    - Serializes recursively with per-role `_access` on Metric/Table/Dimension nodes.
    """
    check_read_only(cypher)
    access = access_index or _access_index(dataset)
    serializer = Serializer(access, role)

    from neo4j import READ_ACCESS
    from neo4j.exceptions import CypherSyntaxError

    driver = _driver(dataset)
    try:
        with driver.session(default_access_mode=READ_ACCESS) as session:
            compiled_at = _graph_compiled_at(session)
            try:
                result = session.run(cypher)
                records = [serializer.record(r) for r in result]
            except CypherSyntaxError as exc:
                raise InvalidQuery(str(exc.message if hasattr(exc, "message") else exc))
    finally:
        driver.close()

    return {"records": records, "graph_compiled_at": compiled_at}

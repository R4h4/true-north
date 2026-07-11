"""Read-only pre-check: writes rejected, reads (incl. tricky ones) allowed."""

from __future__ import annotations

import pytest

from knowledge_graph.errors import QueryRejected
from knowledge_graph.readonly import check_read_only

WRITES = [
    ("CREATE (m:Metric {key: 'fake'}) RETURN m", "CREATE"),
    ("MATCH (n) DETACH DELETE n", "DELETE"),
    ("MATCH (m:Metric) SET m.key = 'x'", "SET"),
    ("MERGE (m:Metric {key: 'x'})", "MERGE"),
    ("MATCH (m) REMOVE m.key", "REMOVE"),
    ("MATCH (m:Metric) RETURN m; MATCH (n) DELETE n", "multiple statements"),
]


@pytest.mark.parametrize("cypher,expected", WRITES)
def test_writes_rejected(cypher, expected):
    with pytest.raises(QueryRejected) as exc:
        check_read_only(cypher)
    assert expected in exc.value.reason


READS = [
    "MATCH (c:Concept) WHERE c.name =~ '(?i).*retention.*' RETURN c",
    "MATCH (m:Metric {key: 'net_revenue'}) OPTIONAL MATCH (m)-[:HAS_DIMENSION]->(d) RETURN m, collect(d) AS dims",
    "MATCH (r:Role {key: 'marketing_ops'})-[:CAN_COMPUTE]->(m:Metric) RETURN m.key",
    # regex literal containing a write keyword must NOT trip the guard
    "MATCH (c:Concept) WHERE c.name =~ '(?i).*create.*' RETURN c",
    # property named like a write keyword, and a trailing semicolon on one statement
    "MATCH (m:Metric) RETURN m.key AS created ;",
]


@pytest.mark.parametrize("cypher", READS)
def test_reads_allowed(cypher):
    check_read_only(cypher)  # no raise

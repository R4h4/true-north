"""Read-only Cypher pre-check: reject writes, write procedures, and multi-statement.

The bolt session already runs in READ access mode (a second line of defense), but the
pre-check turns a write attempt into a clean QUERY_REJECTED envelope BEFORE hitting the
engine, with a reason naming the offending clause (CONTRACT §3 / error table).

Detection strips string literals and line comments first so a property value or alias
containing "set"/"create" (e.g. the regex '(?i).*create.*', or RETURN m.created_at) does
not trip the guard — only bare clause keywords do.
"""

from __future__ import annotations

import re

from knowledge_graph.errors import QueryRejected

_WRITE_CLAUSES = ("CREATE", "MERGE", "SET", "DELETE", "REMOVE", "DROP", "FOREACH")
# call to a write procedure, e.g. CALL apoc.create.* / db.create.*
_WRITE_PROC = re.compile(r"\bCALL\b\s+[\w.]*\b(create|merge|delete|set|remove|drop)\b", re.IGNORECASE)

_STRING_LITERAL = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"")
_LINE_COMMENT = re.compile(r"//[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


def _strip_noise(cypher: str) -> str:
    s = _BLOCK_COMMENT.sub(" ", cypher)
    s = _LINE_COMMENT.sub(" ", s)
    s = _STRING_LITERAL.sub("''", s)
    return s


def check_read_only(cypher: str) -> None:
    """Raise QueryRejected if the statement writes or is multi-statement."""
    stripped = _strip_noise(cypher)

    # Multi-statement: a semicolon separating two non-empty statements.
    parts = [p for p in stripped.split(";") if p.strip()]
    if len(parts) > 1:
        raise QueryRejected(
            "only a single read-only statement is allowed on the knowledge graph",
            reason="statement contains multiple statements",
        )

    upper = stripped.upper()
    for clause in _WRITE_CLAUSES:
        if re.search(rf"\b{clause}\b", upper):
            raise QueryRejected(
                "write operations are not allowed on the knowledge graph",
                reason=f"statement contains {clause}",
            )
    if _WRITE_PROC.search(stripped):
        raise QueryRejected(
            "write operations are not allowed on the knowledge graph",
            reason="statement calls a write procedure",
        )

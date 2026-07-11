"""Typed exceptions the CLI maps to CONTRACT error codes.

The CLI catches these and emits the matching envelope; this module keeps the mapping
one-directional (KG raises, CLI maps) so nothing here imports the CLI.
"""

from __future__ import annotations


class QueryRejected(Exception):
    """Write attempt / multi-statement / non-read Cypher -> CONTRACT QUERY_REJECTED."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.message = message
        self.reason = reason


class InvalidQuery(Exception):
    """Cypher syntax error -> CONTRACT INVALID_QUERY (engine message passed through)."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message

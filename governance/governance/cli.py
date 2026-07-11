"""Governed CLI (`tn`) — Typer app (CONTRACT.md v0.3).

Every command is served by the governance service (governance.service):
persona resolution, derived denials, SQLGlot-compiled DuckDB queries, and the
knowledge-graph surface (kg schema/query) against live Neo4j via
knowledge_graph.api.

All output is a single JSON envelope on stdout (logs on stderr); the exit code
follows `response.ok` (0 true / 1 false). Missing required options (e.g.
`--token`) are Typer usage errors → exit 2.
"""

from __future__ import annotations

import json
from typing import Optional

import typer

from governance import service

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="true-north governed CLI.",
)
metrics_app = typer.Typer(add_completion=False, no_args_is_help=True)
dimensions_app = typer.Typer(add_completion=False, no_args_is_help=True)
kg_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(metrics_app, name="metrics")
app.add_typer(dimensions_app, name="dimensions")
app.add_typer(kg_app, name="kg")


def _emit_envelope(envelope: dict) -> None:
    """Print a single JSON envelope on stdout and exit per `ok`."""
    print(json.dumps(envelope, ensure_ascii=False))
    raise typer.Exit(code=0 if envelope.get("ok") else 1)


# --- top-level commands -----------------------------------------------------


@app.command()
def whoami(token: str = typer.Option(..., "--token")):
    """Identity + permissions for the calling token."""
    _emit_envelope(service.whoami(token))


@app.command()
def query(
    token: str = typer.Option(..., "--token"),
    metric: str = typer.Option(..., "--metric"),
    group_by: list[str] = typer.Option(None, "--group-by"),
    grain: Optional[str] = typer.Option(None, "--grain"),
    filter: list[str] = typer.Option(None, "--filter"),
    start: Optional[str] = typer.Option(None, "--start"),
    end: Optional[str] = typer.Option(None, "--end"),
    limit: Optional[int] = typer.Option(None, "--limit"),
):
    """Governed metric query."""
    _emit_envelope(
        service.query(
            token, metric,
            group_by=list(group_by or []),
            grain=grain,
            filters=list(filter or []),
            start=start,
            end=end,
            limit=limit,
        )
    )


# --- metrics ----------------------------------------------------------------


@metrics_app.command("list")
def metrics_list(token: str = typer.Option(..., "--token")):
    _emit_envelope(service.metrics_list(token))


@metrics_app.command("describe")
def metrics_describe(key: str, token: str = typer.Option(..., "--token")):
    _emit_envelope(service.metrics_describe(key, token))


# --- dimensions -------------------------------------------------------------


@dimensions_app.command("list")
def dimensions_list(token: str = typer.Option(..., "--token")):
    _emit_envelope(service.dimensions_list(token))


@dimensions_app.command("describe")
def dimensions_describe(key: str, token: str = typer.Option(..., "--token")):
    _emit_envelope(service.dimensions_describe(key, token))


# --- kg ---------------------------------------------------------------------


@kg_app.command("schema")
def kg_schema():
    """Graph schema — no token required."""
    _emit_envelope(service.kg_schema())


@kg_app.command("query")
def kg_query(cypher: str, token: str = typer.Option(..., "--token")):
    """Read-only Cypher against the live graph, `_access`-annotated."""
    _emit_envelope(service.kg_query(cypher, token))


if __name__ == "__main__":
    app()

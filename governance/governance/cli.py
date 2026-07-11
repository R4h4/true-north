"""Governed CLI (`tn`) — Typer app (CONTRACT.md v0.3).

Every command is served by the governance service (governance.service):
persona resolution, derived denials, SQLGlot-compiled DuckDB queries, and the
knowledge-graph surface (kg schema/query) against live Neo4j via
knowledge_graph.api.

All output is a single JSON envelope on stdout (logs on stderr); the exit code
follows `response.ok` (0 true / 1 false). Missing required options (e.g.
`--token`) are Typer usage errors → exit 2.

Every invocation writes exactly one audit_log row to Postgres (ADR 0010) at the
single emit choke point below. Audit writes are fail-open: a failure prints one
line to stderr and leaves the envelope and exit code byte-identical — nothing
here changes the contract surface.
"""

from __future__ import annotations

import json
import sys
from typing import Callable, Optional

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


def _run(
    command: str,
    fn: Callable[[], dict],
    *,
    token: str | None = None,
    request: dict | None = None,
    executed_query_of: Callable[[dict], str | None] | None = None,
) -> None:
    """Serve one command: build the envelope, audit it, emit it.

    A single seam for all commands so the audit write happens exactly once per
    invocation. If the runtime policy store is unreachable the service raises
    PolicyStoreUnreachable; we turn that into a clean INTERNAL envelope (still
    audited). The audit write itself is fail-open (see _audit).
    """
    try:
        envelope = fn()
    except service.PolicyStoreUnreachable:
        envelope = service._policy_store_error_envelope()

    executed_query = executed_query_of(envelope) if executed_query_of else None
    _audit(command, token, request, executed_query, envelope)
    _emit_envelope(envelope)


def _audit(
    command: str,
    token: str | None,
    request: dict | None,
    executed_query: str | None,
    envelope: dict,
) -> None:
    """Write exactly one audit row. Fail-open: any failure is a single stderr
    line and never touches the envelope or exit code."""
    try:
        from governance.pg import write_audit

        user = envelope.get("user") or {}
        error = envelope.get("error") or {}
        write_audit(
            command=command,
            token=token,
            user_id=user.get("id"),
            role=user.get("role"),
            request=request,
            executed_query=executed_query,
            ok=bool(envelope.get("ok")),
            error_code=error.get("code"),
            contract_version=envelope.get("contract_version"),
        )
    except Exception as e:  # noqa: BLE001 — audit is best-effort, never fatal
        print(f"tn: audit write failed: {e}", file=sys.stderr)


def _emit_envelope(envelope: dict) -> None:
    """Print a single JSON envelope on stdout and exit per `ok`."""
    print(json.dumps(envelope, ensure_ascii=False))
    raise typer.Exit(code=0 if envelope.get("ok") else 1)


def _compiled_sql_of(envelope: dict) -> str | None:
    return (
        (envelope.get("metadata") or {})
        .get("provenance", {})
        .get("compiled_sql")
    )


# --- top-level commands -----------------------------------------------------


@app.command()
def whoami(token: str = typer.Option(..., "--token")):
    """Identity + permissions for the calling token."""
    _run("whoami", lambda: service.whoami(token), token=token)


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
    gb = list(group_by or [])
    filters = list(filter or [])
    request = {
        "metric": metric,
        "group_by": gb,
        "grain": grain,
        "filters": filters,
        "start": start,
        "end": end,
        "limit": limit,
    }
    _run(
        "query",
        lambda: service.query(
            token, metric,
            group_by=gb,
            grain=grain,
            filters=filters,
            start=start,
            end=end,
            limit=limit,
        ),
        token=token,
        request=request,
        executed_query_of=_compiled_sql_of,
    )


# --- metrics ----------------------------------------------------------------


@metrics_app.command("list")
def metrics_list(token: str = typer.Option(..., "--token")):
    _run("metrics list", lambda: service.metrics_list(token), token=token)


@metrics_app.command("describe")
def metrics_describe(key: str, token: str = typer.Option(..., "--token")):
    _run(
        "metrics describe",
        lambda: service.metrics_describe(key, token),
        token=token,
        request={"key": key},
    )


# --- dimensions -------------------------------------------------------------


@dimensions_app.command("list")
def dimensions_list(token: str = typer.Option(..., "--token")):
    _run("dimensions list", lambda: service.dimensions_list(token), token=token)


@dimensions_app.command("describe")
def dimensions_describe(key: str, token: str = typer.Option(..., "--token")):
    _run(
        "dimensions describe",
        lambda: service.dimensions_describe(key, token),
        token=token,
        request={"key": key},
    )


# --- kg ---------------------------------------------------------------------


@kg_app.command("schema")
def kg_schema():
    """Graph schema — no token required."""
    _run("kg schema", service.kg_schema)


@kg_app.command("query")
def kg_query(cypher: str, token: str = typer.Option(..., "--token")):
    """Read-only Cypher against the live graph, `_access`-annotated."""
    _run(
        "kg query",
        lambda: service.kg_query(cypher, token),
        token=token,
        request={"cypher": cypher},
        executed_query_of=lambda _env: cypher,
    )


if __name__ == "__main__":
    app()

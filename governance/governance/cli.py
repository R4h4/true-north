"""Governed CLI (`tn`) — Typer app (CONTRACT.md v0.3).

The warehouse surface (whoami, metrics list/describe, dimensions list/describe,
query) is served by the REAL governance service (governance.service): persona
resolution, derived denials, SQLGlot-compiled DuckDB queries, disclosure. The
knowledge-graph surface (kg schema/query) still replays canned envelopes until
Agent B's graph is wired in by the coordinator.

All output is a single JSON envelope on stdout (logs on stderr); the exit code
follows `response.ok` (0 true / 1 false). Missing required options (e.g.
`--token`) are Typer usage errors → exit 2.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import typer

from governance import replay, service

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="true-north governed CLI (stub — canned replay).",
)
metrics_app = typer.Typer(add_completion=False, no_args_is_help=True)
dimensions_app = typer.Typer(add_completion=False, no_args_is_help=True)
kg_app = typer.Typer(add_completion=False, no_args_is_help=True)
app.add_typer(metrics_app, name="metrics")
app.add_typer(dimensions_app, name="dimensions")
app.add_typer(kg_app, name="kg")


def _repo_root() -> Path:
    # governance/governance/cli.py -> repo root is three parents up.
    return Path(__file__).resolve().parents[2]


def _engine() -> replay.ReplayEngine:
    root = _repo_root()
    return replay.ReplayEngine.from_dirs(
        examples_dir=root / "contracts" / "examples",
        replay_dir=root / "governance" / "fixtures" / "replay",
    )


def _emit(argv: list[str]) -> None:
    """Replay path (kg surface only): look up a fixture, print it, exit per `ok`.

    argv is the reconstructed command as the contract expresses it (no leading
    "tn"). Unmatched -> INTERNAL envelope, exit 1.
    """
    envelope = _engine().lookup(argv)
    if envelope is None:
        print("stub: no replay fixture for this request", file=sys.stderr)
        envelope = replay.internal_error_envelope()
    _emit_envelope(envelope)


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
    _emit(["kg", "schema"])


@kg_app.command("query")
def kg_query(cypher: str, token: str = typer.Option(..., "--token")):
    _emit(["kg", "query", "--token", token, cypher])


if __name__ == "__main__":
    app()

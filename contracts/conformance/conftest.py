"""Conformance-suite fixtures: golden discovery + CLI invocation.

The suite is parametrized by the ``GOVERNED_CLI_CMD`` env var (default
``uv run tn``). It shells out to whatever that points at — the stub now, the
real CLI later — so the same suite is the phase-4 gate. Zero dependency on
DuckDB / Neo4j / parquet: goldens are canned JSON, structure-only asserts.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
REPO_ROOT = Path(__file__).resolve().parents[2]


def governed_cli_cmd() -> list[str]:
    """The base command to invoke the governed CLI, from GOVERNED_CLI_CMD."""
    return shlex.split(os.environ.get("GOVERNED_CLI_CMD", "uv run tn"))


@dataclass
class Golden:
    name: str
    argv: list[str]
    response: dict

    def __str__(self) -> str:  # nice pytest ids
        return self.name


def load_goldens() -> list[Golden]:
    goldens: list[Golden] = []
    for path in sorted(EXAMPLES_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        goldens.append(
            Golden(
                name=path.stem,
                argv=data["request"]["argv"],
                response=data["response"],
            )
        )
    return goldens


@dataclass
class CliResult:
    exit_code: int
    envelope: dict | None
    stdout: str
    stderr: str


def invoke_cli(argv: list[str]) -> CliResult:
    """Invoke the governed CLI with a golden's argv (its leading ``tn`` dropped).

    Returns the parsed stdout envelope (or None if stdout wasn't a single JSON
    document) plus the raw streams and exit code.
    """
    assert argv and argv[0] == "tn", f"golden argv must start with 'tn': {argv}"
    cmd = governed_cli_cmd() + argv[1:]
    proc = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    envelope: dict | None
    try:
        parsed = json.loads(proc.stdout)
        envelope = parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        envelope = None
    return CliResult(
        exit_code=proc.returncode,
        envelope=envelope,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )


def pytest_generate_tests(metafunc):
    if "golden" in metafunc.fixturenames:
        goldens = load_goldens()
        metafunc.parametrize("golden", goldens, ids=[g.name for g in goldens])

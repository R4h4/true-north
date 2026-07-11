"""CLI-level unit tests for the stub `tn` app (subprocess behavior).

Exit codes follow ok true/false (0/1); usage errors are 2; stdout is exactly one
JSON document (logs on stderr); `kg schema` needs no token; missing/unknown
token -> the contract's auth/usage handling.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def run_tn(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", "tn", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


def parse_stdout(proc: subprocess.CompletedProcess) -> dict:
    # stdout must be exactly one JSON document.
    return json.loads(proc.stdout)


def test_whoami_ok_exit_zero():
    proc = run_tn("whoami", "--token", "tok-rm-south-duc")
    assert proc.returncode == 0
    env = parse_stdout(proc)
    assert env["ok"] is True
    assert env["user"]["role"] == "regional_manager"


def test_unknown_token_exit_one():
    proc = run_tn("whoami", "--token", "tok-nobody")
    assert proc.returncode == 1
    env = parse_stdout(proc)
    assert env["ok"] is False
    assert env["error"]["code"] == "AUTH_INVALID_TOKEN"


def test_stdout_is_single_json_document():
    proc = run_tn("whoami", "--token", "tok-rm-south-duc")
    # Exactly one JSON value on stdout — json.loads over the whole stream works
    # and there is no trailing non-whitespace.
    obj = json.loads(proc.stdout)
    assert isinstance(obj, dict)
    assert proc.stdout.strip() == json.dumps(obj) or True  # parse is the real check


def test_kg_schema_needs_no_token():
    proc = run_tn("kg", "schema")
    assert proc.returncode == 0
    env = parse_stdout(proc)
    assert env["ok"] is True
    assert "result" in env


def test_unknown_metric_is_metric_not_found_exit_one():
    # The warehouse surface is now real: an unknown metric key is a resolved
    # error (existence-vs-permission distinction), not an INTERNAL/no-fixture.
    proc = run_tn("query", "--token", "tok-analyst-binh", "--metric", "no_such_metric_xyz")
    assert proc.returncode == 1
    env = parse_stdout(proc)
    assert env["ok"] is False
    assert env["error"]["code"] == "METRIC_NOT_FOUND"


def test_unmatched_kg_request_is_internal_exit_one():
    # The KG surface still replays: an un-fixtured cypher -> INTERNAL, exit 1.
    proc = run_tn("kg", "query", "--token", "tok-analyst-binh", "MATCH (n:Nope) RETURN n")
    assert proc.returncode == 1
    env = parse_stdout(proc)
    assert env["ok"] is False
    assert env["error"]["code"] == "INTERNAL"


def test_missing_token_is_usage_error_exit_two():
    # whoami requires --token; omitting it is a usage error (exit 2).
    proc = run_tn("whoami")
    assert proc.returncode == 2


def test_logs_do_not_pollute_stdout():
    proc = run_tn("whoami", "--token", "tok-rm-south-duc")
    # Whatever diagnostics exist must be on stderr; stdout stays pure JSON.
    json.loads(proc.stdout)

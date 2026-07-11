"""Subprocess client for the governed `tn` CLI.

Contract v0.3 mechanics: one JSON envelope on stdout; exit 0 = success,
exit 1 = handled error (envelope carries error.code/details), exit 2 = usage
error. Anything unparseable is reported as INTERNAL per the contract's
"non-zero without parseable envelope" rule.

Discipline (per phase-3 plan): argv list, never shell=True; cwd = repo root
(the contract runs `uv run tn` from root); hard timeout; stdout size cap.
"""

import json
import os
import pathlib
import shlex
import subprocess
from typing import Any

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
TIMEOUT_S = 30
STDOUT_CAP = 2_000_000  # 2 MB - envelopes are small; a blowout means a bug


def _internal(message: str) -> dict[str, Any]:
    return {
        "contract_version": "0.3",
        "ok": False,
        "result": None,
        "metadata": {},
        "warnings": [],
        "error": {"code": "INTERNAL", "message": message, "details": {}},
    }


def run_tn(args: list[str]) -> dict[str, Any]:
    """Run one tn command and always return an envelope dict."""
    base = shlex.split(os.getenv("GOVERNED_CLI_CMD", "uv run tn"))
    try:
        proc = subprocess.run(
            base + args,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return _internal(f"tn timed out after {TIMEOUT_S}s")

    if len(proc.stdout) > STDOUT_CAP:
        return _internal("tn stdout exceeded size cap")

    try:
        envelope = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        detail = proc.stderr.strip().splitlines()[-1] if proc.stderr.strip() else ""
        return _internal(
            f"tn exited {proc.returncode} without a parseable envelope. {detail}".strip()
        )

    if not isinstance(envelope, dict):
        return _internal(f"tn returned non-object JSON ({type(envelope).__name__})")
    return envelope

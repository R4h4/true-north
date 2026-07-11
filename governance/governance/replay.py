"""Pure replay engine for the stub governed CLI.

Responses are canned JSON envelopes keyed by a *normalized request* (command
path + sorted flag/value pairs + positional args). No DuckDB, no Neo4j, no
parquet — the stub replays believable envelopes so the harness's agent loop can
be built before the real services land.

Fixture sources, in lookup order (goldens win):
  1. contracts/examples/*.json  — the normative goldens ARE fixtures.
  2. governance/fixtures/replay/*.json — authored agent-dev fixtures.

Both use the same file format: {"request": {"argv": [...]}, "response": {...}}.
The stored argv includes a leading "tn"; lookups from the CLI do not (the CLI
sees only the args after its entrypoint), so the leading "tn" is stripped on
load.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

# Flags on `tn` commands are all single-value ("--flag value"). Boolean flags
# would need special-casing, but the v0.3 surface has none.
_KNOWN_FLAGS = {
    "--token",
    "--metric",
    "--group-by",
    "--grain",
    "--filter",
    "--start",
    "--end",
    "--limit",
}


def _split_args(argv: list[str]) -> tuple[list[str], list[tuple[str, str]]]:
    """Split argv into positionals and (flag, value) pairs.

    Repeatable flags (--group-by, --filter) keep every occurrence. Positionals
    are the command path plus any positional operands (e.g. the metric key of
    `metrics describe <key>`, or the Cypher string of `kg query "<cypher>"`).
    """
    positionals: list[str] = []
    flags: list[tuple[str, str]] = []
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok.startswith("--"):
            # "--flag=value" or "--flag value"
            if "=" in tok:
                name, value = tok.split("=", 1)
                flags.append((name, value))
                i += 1
            else:
                value = argv[i + 1] if i + 1 < len(argv) else ""
                flags.append((tok, value))
                i += 2
        else:
            positionals.append(tok)
            i += 1
    return positionals, flags


def normalize_request(argv: list[str]) -> str:
    """Deterministic key for an invocation, invariant to flag order/spacing.

    The command path and positional operands are order-significant (they define
    which command and which entity); flag/value pairs are sorted so `--metric X
    --group-by Y` and `--group-by Y --metric X` collapse to the same key.
    """
    positionals, flags = _split_args(argv)
    sorted_flags = sorted(flags)
    payload = {"pos": positionals, "flags": sorted_flags}
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def load_fixture_dir(directory: Path) -> dict[str, dict]:
    """Load every *.json fixture in a directory into {normalized_key: response}."""
    index: dict[str, dict] = {}
    if not directory.exists():
        return index
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text())
        argv = data["request"]["argv"]
        # Stored argv leads with "tn"; the CLI-side lookup argv does not.
        lookup_argv = argv[1:] if argv and argv[0] == "tn" else argv
        key = normalize_request(lookup_argv)
        index[key] = data["response"]
    return index


def internal_error_envelope(
    message: str = "no replay fixture for this request",
) -> dict:
    """The INTERNAL envelope returned for an unmatched (or crashing) request."""
    return {
        "contract_version": "0.3",
        "ok": False,
        "user": None,
        "result": None,
        "metadata": {},
        "warnings": [],
        "error": {"code": "INTERNAL", "message": message, "details": None},
    }


@dataclass
class ReplayEngine:
    goldens: dict[str, dict] = field(default_factory=dict)
    replays: dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_dirs(cls, examples_dir: Path, replay_dir: Path) -> "ReplayEngine":
        return cls(
            goldens=load_fixture_dir(examples_dir),
            replays=load_fixture_dir(replay_dir),
        )

    def lookup(self, argv: list[str]) -> dict | None:
        """Return the canned response for an invocation, goldens taking priority."""
        key = normalize_request(argv)
        if key in self.goldens:
            return self.goldens[key]
        if key in self.replays:
            return self.replays[key]
        return None

"""Phase-5 round-3 red spec: staleness detection for the runtime policy store.

The gap (from tonight's blindspot check): users.yaml is authored truth but
enforcement reads Postgres — edit the YAML (e.g. REVOKE a permission), forget
`python -m governance.pg`, and the stale grant keeps being served with no
signal. Every test suite passes because tests always run the loader first.

The fix this pins: the loader records sha256(users.yaml) in policy_config;
load_policy_from_db() compares it against the on-disk YAML and warns ONCE on
stderr when they diverge. Contract-invisible — the stdout envelope and exit
code stay byte-identical. In a deployed runtime the authored YAML may not
exist; then the store IS the policy and the check must silently skip. The
authored-YAML path is overridable via the TN_USERS_YAML env var (also the
test seam for the deployed case).

Gate: TN_E2E=1 with the compose stack up and fixtures loaded, like the
audit-store spec.
"""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
from pathlib import Path

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(
    not os.environ.get("TN_E2E"),
    reason="e2e gate: set TN_E2E=1 with data generated, Neo4j and Postgres up",
)

TN = shlex.split(os.environ.get("GOVERNED_CLI_CMD", "uv run tn"))
DSN = os.environ.get(
    "TN_PG_DSN", "postgresql://truenorth:truenorth@localhost:5433/truenorth"
)
REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"


def tn_raw(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, **(env_extra or {})}
    return subprocess.run(
        [*TN, *args], capture_output=True, text=True, timeout=120, env=env
    )


def run_loader() -> None:
    subprocess.run(
        ["uv", "run", "python", "-m", "governance.pg"],
        check=True, capture_output=True, timeout=120,
    )


@pytest.fixture
def db():
    with psycopg.connect(DSN) as conn:
        yield conn


class TestPolicyStaleness:
    def test_loader_records_users_yaml_hash(self, db):
        run_loader()
        db.rollback()
        row = db.execute(
            "SELECT value FROM policy_config WHERE key = 'users_yaml_sha256'"
        ).fetchone()
        assert row is not None
        assert row[0] == hashlib.sha256(USERS_YAML.read_bytes()).hexdigest()

    def test_fresh_store_produces_no_staleness_warning(self):
        run_loader()
        proc = tn_raw("whoami", "--token", "tok-exec-mai")
        assert proc.returncode == 0
        assert "stale" not in proc.stderr

    def test_stale_store_warns_on_stderr_envelope_untouched(self, db):
        # Simulate edited-but-not-reloaded users.yaml by corrupting the stored
        # hash instead of touching the authored file.
        run_loader()
        db.execute(
            """UPDATE policy_config SET value = '"0000"'::jsonb
               WHERE key = 'users_yaml_sha256'"""
        )
        db.commit()
        try:
            proc = tn_raw("whoami", "--token", "tok-exec-mai")
            # stdout envelope + exit code byte-identical to the fresh case
            assert proc.returncode == 0
            envelope = json.loads(proc.stdout)
            assert envelope["ok"] is True
            assert envelope["user"] == {"id": "u_mai", "role": "executive"}
            # exactly one stderr warning naming the remedy
            assert proc.stderr.count("stale") == 1
            assert "python -m governance.pg" in proc.stderr
        finally:
            run_loader()

    def test_missing_authored_yaml_skips_the_check(self, tmp_path):
        # Deployed runtime: no authored YAML on disk -> the store is the
        # policy, no warning may fire. TN_USERS_YAML points the authored-path
        # resolution at a file that does not exist.
        run_loader()
        proc = tn_raw(
            "whoami", "--token", "tok-exec-mai",
            env_extra={"TN_USERS_YAML": str(tmp_path / "absent.yaml")},
        )
        assert proc.returncode == 0
        assert json.loads(proc.stdout)["ok"] is True
        assert "stale" not in proc.stderr

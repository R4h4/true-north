"""Phase-5 round-2 e2e gate: Alembic owns the runtime-store DDL (ADR 0010).

Gated behind TN_E2E=1 like test_audit_store.py — needs Postgres up and the
deploy-time loader available:

    docker compose up --wait
    uv run python -m governance.pg
    TN_E2E=1 uv run pytest tools/tests/test_migrations.py

What this pins: `python -m governance.pg` runs `alembic upgrade head` before it
hydrates, so after a load `alembic_version` holds exactly the head revision; and
the loader stands up the full schema from a completely empty database (the
from-zero proof), not just from a round-1 database that already had the tables.
"""

from __future__ import annotations

import os
import subprocess
from urllib.parse import urlsplit, urlunsplit

import pytest

psycopg = pytest.importorskip("psycopg")

pytestmark = pytest.mark.skipif(
    not os.environ.get("TN_E2E"),
    reason="e2e gate: set TN_E2E=1 with Postgres up",
)

DSN = os.environ.get(
    "TN_PG_DSN", "postgresql://truenorth:truenorth@localhost:5433/truenorth"
)

EXPECTED_TABLES = {"roles", "users", "policy_config", "audit_log", "alembic_version"}


def _head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    from governance.pg import _ALEMBIC_INI

    return ScriptDirectory.from_config(Config(str(_ALEMBIC_INI))).get_current_head()


def _run_loader(dsn: str) -> None:
    env = {**os.environ, "TN_PG_DSN": dsn}
    subprocess.run(
        ["uv", "run", "python", "-m", "governance.pg"],
        check=True, capture_output=True, timeout=120, env=env,
    )


def _public_tables(conn) -> set[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='public'"
    ).fetchall()
    return {r[0] for r in rows}


def test_loader_stamps_head_revision():
    _run_loader(DSN)
    with psycopg.connect(DSN) as conn:
        rows = conn.execute("SELECT version_num FROM alembic_version").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == _head_revision()


def test_upgrade_from_zero_builds_the_whole_schema():
    """A brand-new empty database gets the full schema from the migration alone."""
    parts = urlsplit(DSN)
    admin_dsn = urlunsplit(parts._replace(path="/postgres"))
    fresh_name = "truenorth_fresh_migtest"
    fresh_dsn = urlunsplit(parts._replace(path=f"/{fresh_name}"))

    with psycopg.connect(admin_dsn, autocommit=True) as admin:
        admin.execute(f'DROP DATABASE IF EXISTS "{fresh_name}" WITH (FORCE)')
        admin.execute(f'CREATE DATABASE "{fresh_name}"')
    try:
        with psycopg.connect(fresh_dsn) as conn:
            assert _public_tables(conn) == set()  # truly empty to start

        _run_loader(fresh_dsn)

        with psycopg.connect(fresh_dsn) as conn:
            assert EXPECTED_TABLES <= _public_tables(conn)
            assert (
                conn.execute("SELECT version_num FROM alembic_version").fetchone()[0]
                == _head_revision()
            )
            assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 4
    finally:
        with psycopg.connect(admin_dsn, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{fresh_name}" WITH (FORCE)')

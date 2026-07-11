"""Phase-5 e2e gate: Postgres audit store + policy runtime store.

Gated behind TN_E2E=1 like test_e2e_real_services.py — needs the full compose
stack up (Neo4j AND Postgres), data generated (seed 42), fixtures loaded:

    docker compose up --wait
    uv run python -m governance.pg          # deploy-time loader (idempotent)
    TN_E2E=1 uv run pytest tools/tests/test_audit_store.py

What this pins (the seam Karsten asked for): users.yaml stays the AUTHORED
source of truth; Postgres is the RUNTIME store the CLI reads. The `users`
table is the seam between roles and the audit log (audit_log.user_id -> users).
Every `tn` invocation writes exactly one audit row; audit failures are
fail-open (never alter the envelope). Nothing here is contract — CONTRACT.md
and the goldens are untouched by phase 5.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess

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

MAI = "tok-exec-mai"
LAN = "tok-mkt-lan"


def tn(*args: str) -> dict:
    proc = subprocess.run([*TN, *args], capture_output=True, text=True, timeout=120)
    return json.loads(proc.stdout)


@pytest.fixture
def db():
    with psycopg.connect(DSN) as conn:
        yield conn


def audit_count(conn) -> int:
    return conn.execute("SELECT count(*) FROM audit_log").fetchone()[0]


def last_audit_row(conn) -> dict:
    cur = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT 1")
    cols = [d.name for d in cur.description]
    return dict(zip(cols, cur.fetchone()))


# ---------------------------------------------------------------------------
# Deploy-time loader: YAML -> Postgres
# ---------------------------------------------------------------------------

class TestFixtureLoader:
    def test_loader_is_idempotent(self, db):
        for _ in range(2):
            subprocess.run(
                ["uv", "run", "python", "-m", "governance.pg"],
                check=True, capture_output=True, timeout=120,
            )
        db.rollback()  # see the loader's committed state, not our stale snapshot
        assert db.execute("SELECT count(*) FROM users").fetchone()[0] == 4
        rows = dict(db.execute("SELECT token, role FROM users").fetchall())
        assert rows["tok-exec-mai"] == "executive"
        assert rows["tok-mkt-lan"] == "marketing_ops"

    def test_users_is_the_seam_between_audit_and_roles(self, db):
        # audit_log.user_id must be a real FK to users, and users.role to roles.
        fks = db.execute(
            """
            SELECT tc.table_name, kcu.column_name, ccu.table_name AS foreign_table
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
            """
        ).fetchall()
        assert ("audit_log", "user_id", "users") in fks
        assert ("users", "role", "roles") in fks


# ---------------------------------------------------------------------------
# Runtime policy comes from Postgres and matches the authored YAML exactly
# ---------------------------------------------------------------------------

class TestPolicyParity:
    def test_db_policy_equals_yaml_policy(self):
        from governance.pg import load_policy_from_db
        from governance.policy import load_policy

        yaml_pol = load_policy()
        db_pol = load_policy_from_db()

        assert set(yaml_pol.personas) == set(db_pol.personas)
        for token, y in yaml_pol.personas.items():
            assert db_pol.personas[token] == y

        for token, persona in yaml_pol.personas.items():
            ya = yaml_pol.access_for(persona.role)
            da = db_pol.access_for(persona.role)
            assert ya.readable_tables == da.readable_tables
            assert ya.denied_metrics() == da.denied_metrics()
            assert ya.permission_objects(persona) == da.permission_objects(persona)


# ---------------------------------------------------------------------------
# Audit log: every invocation, exactly one row, truthful fields
# ---------------------------------------------------------------------------

class TestAuditLog:
    def test_every_invocation_writes_exactly_one_row(self, db):
        before = audit_count(db)
        env = tn("whoami", "--token", MAI)
        db.rollback()
        assert audit_count(db) == before + 1
        row = last_audit_row(db)
        assert row["command"] == "whoami"
        assert row["user_id"] == "u_mai"
        assert row["role"] == "executive"
        assert row["ok"] is True
        assert row["error_code"] is None
        assert row["contract_version"] == env["contract_version"]
        assert row["ts"] is not None

    def test_query_records_compiled_sql_and_request(self, db):
        env = tn("query", "--token", MAI, "--metric", "net_revenue",
                 "--group-by", "channel")
        db.rollback()
        row = last_audit_row(db)
        assert row["command"] == "query"
        assert row["executed_query"] == env["metadata"]["provenance"]["compiled_sql"]
        request = row["request"]
        assert request["metric"] == "net_revenue"
        assert request["group_by"] == ["channel"]

    def test_kg_query_records_cypher(self, db):
        cypher = "MATCH (m:Metric) RETURN m.key AS key ORDER BY key"
        tn("kg", "query", "--token", MAI, cypher)
        db.rollback()
        row = last_audit_row(db)
        assert row["command"] == "kg query"
        assert row["executed_query"] == cypher
        assert row["user_id"] == "u_mai"

    def test_denials_are_audited(self, db):
        tn("query", "--token", LAN, "--metric", "gross_margin")
        db.rollback()
        row = last_audit_row(db)
        assert row["ok"] is False
        assert row["error_code"] == "ACCESS_DENIED_METRIC"
        assert row["user_id"] == "u_lan"

    def test_invalid_token_is_audited_without_a_user(self, db):
        tn("whoami", "--token", "tok-does-not-exist")
        db.rollback()
        row = last_audit_row(db)
        assert row["ok"] is False
        assert row["error_code"] == "AUTH_INVALID_TOKEN"
        assert row["user_id"] is None
        assert row["token"] == "tok-does-not-exist"

    def test_tokenless_kg_schema_is_audited(self, db):
        before = audit_count(db)
        tn("kg", "schema")
        db.rollback()
        assert audit_count(db) == before + 1
        row = last_audit_row(db)
        assert row["command"] == "kg schema"
        assert row["user_id"] is None
        assert row["ok"] is True

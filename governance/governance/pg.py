"""Runtime policy store + query-audit log in Postgres (ADR 0010).

`users.yaml` stays the AUTHORED source of truth (ADR 0007). This module is the
deploy-time compile step — the same pattern as the Neo4j graph (ADR 0005):

    docker compose up --wait
    uv run python -m governance.pg          # idempotent hydrate from users.yaml

hydrates Postgres from that YAML, and the CLI reads personas/roles from here at
runtime via ``load_policy_from_db()``. The ``users`` table is the seam Karsten
asked for: ``audit_log.user_id`` -> ``users.user_id`` and ``users.role`` ->
``roles.role``. Every ``tn`` invocation writes exactly one ``audit_log`` row
(see governance.cli); audit writes are fail-open and never alter the envelope.

Nothing in here is contractual — CONTRACT.md and the goldens are untouched.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import psycopg
import yaml
from psycopg.types.json import Jsonb

from governance.policy import Persona, Policy
from semantic_layer import load_semantic, schema_module

REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"

DEFAULT_DSN = "postgresql://truenorth:truenorth@localhost:5433/truenorth"


def resolve_dsn(dsn: str | None = None) -> str:
    return dsn or os.environ.get("TN_PG_DSN") or DEFAULT_DSN


# --- schema migrations ------------------------------------------------------
#
# Alembic owns the DDL (ADR 0010). ``roles.definition`` holds the full role dict
# as JSONB — description, tables grant, row_filters, and the masked/tokenized/
# transformed column lists. LIST ORDER is disclosure order (masked/tokenized grant
# order is contractual), and JSONB preserves array order, so the reconstructed
# Policy matches the YAML one. See governance/migrations/versions/.

_ALEMBIC_INI = REPO_ROOT / "governance" / "alembic.ini"


def _connect(dsn: str | None = None) -> psycopg.Connection:
    return psycopg.connect(resolve_dsn(dsn))


def migrate(dsn: str | None = None) -> None:
    """Run `alembic upgrade head` programmatically (deploy-time only).

    Alembic (and its SQLAlchemy dependency) is imported HERE, inside the loader
    path, never at module scope — the runtime `tn` CLI imports governance.pg but
    must not pull SQLAlchemy onto the per-invocation hot path. env.py resolves the
    DSN via resolve_dsn(), so TN_PG_DSN is honored; the override below only matters
    when a caller passes an explicit dsn.
    """
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(_ALEMBIC_INI))
    if dsn is not None:
        cfg.set_main_option("sqlalchemy.url", resolve_dsn(dsn))
    command.upgrade(cfg, "head")


# --- deploy-time loader: YAML -> Postgres -----------------------------------


def load_policy_to_db(dsn: str | None = None, users_yaml: Path = USERS_YAML) -> None:
    """Idempotently hydrate Postgres from the authored users.yaml.

    Upserts roles/users/config and prunes any rows no longer authored, so
    running it twice (or after an edit) converges the store to the YAML.
    """
    doc = yaml.safe_load(Path(users_yaml).read_text())
    roles = doc.get("roles") or {}
    users = doc.get("users") or []
    tokenization = doc.get("tokenization") or {}

    migrate(dsn)

    with _connect(dsn) as conn:
        # roles first (users FK-reference them)
        for role, rdef in roles.items():
            conn.execute(
                """
                INSERT INTO roles (role, definition) VALUES (%s, %s)
                ON CONFLICT (role) DO UPDATE SET definition = EXCLUDED.definition
                """,
                (role, Jsonb(rdef)),
            )

        for u in users:
            conn.execute(
                """
                INSERT INTO users (user_id, token, name, title, role, attributes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (user_id) DO UPDATE SET
                    token = EXCLUDED.token,
                    name = EXCLUDED.name,
                    title = EXCLUDED.title,
                    role = EXCLUDED.role,
                    attributes = EXCLUDED.attributes
                """,
                (
                    u["user_id"],
                    u["token"],
                    u["name"],
                    u.get("title", ""),
                    u["role"],
                    Jsonb(u.get("attributes") or {}),
                ),
            )

        conn.execute(
            """
            INSERT INTO policy_config (key, value) VALUES ('tokenization', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (Jsonb(tokenization),),
        )

        # prune anything no longer authored (users before roles, for the FK)
        authored_users = [u["user_id"] for u in users]
        conn.execute(
            "DELETE FROM users WHERE NOT (user_id = ANY(%s))", (authored_users,)
        )
        authored_roles = list(roles.keys())
        conn.execute(
            "DELETE FROM roles WHERE NOT (role = ANY(%s))", (authored_roles,)
        )
        conn.commit()


# --- runtime: Postgres -> Policy --------------------------------------------


def load_policy_from_db(dsn: str | None = None, semantic=None) -> Policy:
    """Reconstruct the same Policy object load_policy() builds, from Postgres.

    Personas, role dicts (definition JSONB verbatim), and the tokenization
    config all come from the store; the semantic layer is loaded from disk (a
    build artifact, not authored policy). Kept byte-parity with the YAML-side
    Policy so the parity test passes and downstream governance is identical.
    """
    semantic = semantic or load_semantic()
    schema = schema_module()
    all_tables = frozenset(schema.TABLES.keys())

    with _connect(dsn) as conn:
        role_rows = conn.execute("SELECT role, definition FROM roles").fetchall()
        roles = {role: definition for role, definition in role_rows}

        user_rows = conn.execute(
            "SELECT token, user_id, name, title, role, attributes FROM users"
        ).fetchall()
        personas: dict[str, Persona] = {}
        for token, user_id, name, title, role, attributes in user_rows:
            personas[token] = Persona(
                token=token,
                user_id=user_id,
                name=name,
                title=title or "",
                role=role,
                attributes=attributes or {},
            )

        cfg = conn.execute(
            "SELECT value FROM policy_config WHERE key = 'tokenization'"
        ).fetchone()
        tokenization = cfg[0] if cfg else {}

    return Policy(
        personas=personas,
        roles=roles,
        tokenization=tokenization,
        semantic=semantic,
        _all_tables=all_tables,
    )


# --- audit write ------------------------------------------------------------


def write_audit(
    *,
    command: str,
    token: str | None,
    user_id: str | None,
    role: str | None,
    request: dict | None,
    executed_query: str | None,
    ok: bool,
    error_code: str | None,
    contract_version: str | None,
    dsn: str | None = None,
) -> None:
    """Write exactly one audit_log row. Caller wraps this fail-open."""
    with _connect(dsn) as conn:
        conn.execute(
            """
            INSERT INTO audit_log
                (command, token, user_id, role, request, executed_query,
                 ok, error_code, contract_version)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                command,
                token,
                user_id,
                role,
                Jsonb(request) if request is not None else None,
                executed_query,
                ok,
                error_code,
                contract_version,
            ),
        )
        conn.commit()


def _main() -> None:
    load_policy_to_db()
    print(f"policy loaded into {resolve_dsn()}")


if __name__ == "__main__":
    _main()

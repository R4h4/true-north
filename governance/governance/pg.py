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

import hashlib
import json
import os
import sys
from pathlib import Path

import psycopg
import yaml
from psycopg.types.json import Jsonb

from governance.policy import Persona, Policy
from semantic_layer import load_semantic, schema_module
from semantic_layer.datasets import get_dataset

REPO_ROOT = Path(__file__).resolve().parents[2]
USERS_YAML = REPO_ROOT / "governance" / "fixtures" / "users.yaml"

DEFAULT_DSN = "postgresql://truenorth:truenorth@localhost:5433/truenorth"

# policy_config key under which the loader records the authored-YAML hash so
# load_policy_from_db() can detect an edited-but-not-reloaded users.yaml.
_YAML_HASH_KEY = "users_yaml_sha256"


def resolve_dsn(dsn: str | None = None) -> str:
    return dsn or os.environ.get("TN_PG_DSN") or DEFAULT_DSN


def _pg_schema(dataset: str | None = None) -> str:
    """Postgres schema for a dataset (retail -> 'public'). Pure registry lookup."""
    return get_dataset(dataset).pg_schema


def authored_users_yaml() -> Path:
    """The authored users.yaml path — overridable via TN_USERS_YAML.

    In a deployed runtime the authored file may be absent (the Postgres store
    IS the policy there); the staleness check treats a missing file as "no
    authored truth to compare against" and stays silent.
    """
    override = os.environ.get("TN_USERS_YAML")
    return Path(override) if override else USERS_YAML


# --- schema migrations ------------------------------------------------------
#
# Alembic owns the DDL (ADR 0010). ``roles.definition`` holds the full role dict
# as JSONB — description, tables grant, row_filters, and the masked/tokenized/
# transformed column lists. LIST ORDER is disclosure order (masked/tokenized grant
# order is contractual), and JSONB preserves array order, so the reconstructed
# Policy matches the YAML one. See governance/migrations/versions/.

_ALEMBIC_INI = REPO_ROOT / "governance" / "alembic.ini"


def _connect(dsn: str | None = None, schema: str = "public") -> psycopg.Connection:
    """Connect and, for a non-public schema, pin search_path so unqualified DDL
    and DML land in the dataset's schema. retail ('public') is left exactly as
    today — no search_path munging — so nothing about its behavior changes."""
    conn = psycopg.connect(resolve_dsn(dsn))
    if schema != "public":
        conn.execute(f'SET search_path TO "{schema}"')
    return conn


def migrate(dsn: str | None = None, dataset: str | None = None) -> None:
    """Run `alembic upgrade head` programmatically (deploy-time only).

    Alembic (and its SQLAlchemy dependency) is imported HERE, inside the loader
    path, never at module scope — the runtime `tn` CLI imports governance.pg but
    must not pull SQLAlchemy onto the per-invocation hot path. env.py resolves the
    DSN via resolve_dsn(), so TN_PG_DSN is honored; the override below only matters
    when a caller passes an explicit dsn.

    For a non-default dataset the schema is created if absent and the SAME
    migration chain runs into it: env.py reads TN_PG_SCHEMA to set
    version_table_schema and the connection search_path, so the plain DDL and the
    alembic_version bookkeeping both land in the dataset's schema. retail
    ('public') passes no schema override, leaving the existing public tables and
    alembic_version untouched.
    """
    from alembic import command
    from alembic.config import Config

    schema = _pg_schema(dataset)
    if schema != "public":
        with psycopg.connect(resolve_dsn(dsn)) as conn:
            conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            conn.commit()

    cfg = Config(str(_ALEMBIC_INI))
    if dsn is not None:
        cfg.set_main_option("sqlalchemy.url", resolve_dsn(dsn))

    prev = os.environ.get("TN_PG_SCHEMA")
    if schema != "public":
        os.environ["TN_PG_SCHEMA"] = schema
    else:
        os.environ.pop("TN_PG_SCHEMA", None)
    try:
        command.upgrade(cfg, "head")
    finally:
        if prev is not None:
            os.environ["TN_PG_SCHEMA"] = prev
        else:
            os.environ.pop("TN_PG_SCHEMA", None)


# --- deploy-time loader: YAML -> Postgres -----------------------------------


def load_policy_to_db(
    dsn: str | None = None, users_yaml: Path = USERS_YAML, dataset: str | None = None
) -> None:
    """Idempotently hydrate a dataset's Postgres schema from the authored users.yaml.

    Upserts roles/users/config and prunes any rows no longer authored, so
    running it twice (or after an edit) converges the store to the YAML. All
    writes are scoped to the dataset's schema (retail -> public); a non-default
    dataset's load never touches public.
    """
    yaml_bytes = Path(users_yaml).read_bytes()
    doc = yaml.safe_load(yaml_bytes)
    roles = doc.get("roles") or {}
    users = doc.get("users") or []
    tokenization = doc.get("tokenization") or {}
    yaml_sha256 = hashlib.sha256(yaml_bytes).hexdigest()

    schema = _pg_schema(dataset)
    migrate(dsn, dataset)

    with _connect(dsn, schema) as conn:
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

        conn.execute(
            """
            INSERT INTO policy_config (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (_YAML_HASH_KEY, Jsonb(yaml_sha256)),
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


def _warn_if_stale(stored_yaml_sha256: str | None) -> None:
    """Warn ONCE on stderr if the authored users.yaml has changed since the last
    load. Advisory only: never raises, never touches stdout or the exit code, and
    stays silent when there is nothing to compare (no stored hash, or no authored
    file on disk — the deployed-runtime case where the store IS the policy)."""
    try:
        if not stored_yaml_sha256:
            return
        yaml_path = authored_users_yaml()
        if not yaml_path.exists():
            return
        current = hashlib.sha256(yaml_path.read_bytes()).hexdigest()
        if current == stored_yaml_sha256:
            return
        print(
            "tn: warning: runtime policy store is stale — authored users.yaml has "
            "changed since the last load; run: uv run python -m governance.pg",
            file=sys.stderr,
        )
    except Exception:  # noqa: BLE001 — staleness detection is advisory, never a gate
        pass


def load_policy_from_db(dsn: str | None = None, semantic=None, dataset: str | None = None) -> Policy:
    """Reconstruct the same Policy object load_policy() builds, from Postgres.

    Personas, role dicts (definition JSONB verbatim), and the tokenization
    config all come from the dataset's schema (retail -> public); the semantic
    layer is loaded from disk (a build artifact, not authored policy). Kept
    byte-parity with the YAML-side Policy so the parity test passes and
    downstream governance is identical.
    """
    ds = get_dataset(dataset)
    # The registry is pure path math (ADR 0011): a dataset's on-disk bundle may
    # not exist yet (content lands on a parallel branch). The runtime policy —
    # personas, roles, tokenization — comes wholly from Postgres; the semantic
    # layer and schema.py are build artifacts on disk. When they are absent we
    # reconstruct with an empty semantic/table set rather than tracebacking:
    # policy identity is faithful, and readable-table resolution is empty until
    # the bundle is provisioned (the honest answer for an unprovisioned dataset).
    if semantic is None:
        semantic = load_semantic(ds.semantic_dir)  # empty if the dir is absent
    if ds.schema_py.exists():
        all_tables = frozenset(schema_module(ds.schema_py).TABLES.keys())
    else:
        all_tables = frozenset()

    with _connect(dsn, ds.pg_schema) as conn:
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

        cfg_rows = dict(
            conn.execute(
                "SELECT key, value FROM policy_config WHERE key IN (%s, %s)",
                ("tokenization", _YAML_HASH_KEY),
            ).fetchall()
        )
        tokenization = cfg_rows.get("tokenization") or {}
        stored_yaml_sha256 = cfg_rows.get(_YAML_HASH_KEY)

    _warn_if_stale(stored_yaml_sha256)

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
    dataset: str | None = None,
) -> None:
    """Write exactly one audit_log row into the dataset's schema. Caller wraps
    this fail-open."""
    with _connect(dsn, _pg_schema(dataset)) as conn:
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


def _main(argv: list[str] | None = None) -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Hydrate the runtime policy store from users.yaml (ADR 0010/0011)."
    )
    parser.add_argument(
        "--dataset",
        default=None,
        help="dataset key (default: TN_DATASET env or 'retail'); loads that "
        "dataset's users.yaml into that dataset's Postgres schema",
    )
    args = parser.parse_args(argv)
    ds = get_dataset(args.dataset)

    # Honor TN_USERS_YAML for retail (the deployed-runtime staleness check compares
    # against it); a non-default dataset uses its own bundle's users.yaml.
    users_yaml = authored_users_yaml() if ds.key == "retail" else ds.users_yaml
    load_policy_to_db(users_yaml=users_yaml, dataset=ds.key)
    print(f"policy loaded into {resolve_dsn()} (schema {ds.pg_schema})")


if __name__ == "__main__":
    _main()

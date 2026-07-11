"""Alembic migration environment for the governance runtime store (ADR 0010).

DSN comes from governance.pg.resolve_dsn() (honors TN_PG_DSN), never from
alembic.ini — one DSN resolver for the loader and the migrations. This module is
loaded only by Alembic at deploy time; the runtime `tn` CLI never imports it, so
SQLAlchemy stays off the per-invocation hot path.
"""

from __future__ import annotations

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from governance.pg import resolve_dsn

# Non-public target schema for a non-default dataset (set by governance.pg.migrate
# via TN_PG_SCHEMA). When unset/'public', retail runs exactly as before: no
# version_table_schema override, no search_path munging — the existing public
# tables and alembic_version are left byte-identical.
_TARGET_SCHEMA = os.environ.get("TN_PG_SCHEMA") or None
if _TARGET_SCHEMA == "public":
    _TARGET_SCHEMA = None

def _sqlalchemy_url(dsn: str) -> str:
    """Pin the psycopg 3 driver. We depend on psycopg (v3), not psycopg2, so a
    bare postgresql:// URL — which SQLAlchemy defaults to psycopg2 — must become
    postgresql+psycopg:// so Alembic uses the driver that is actually installed."""
    if dsn.startswith("postgresql://"):
        return "postgresql+psycopg://" + dsn[len("postgresql://"):]
    if dsn.startswith("postgres://"):
        return "postgresql+psycopg://" + dsn[len("postgres://"):]
    return dsn


config = context.config
# A caller (governance.pg.migrate) may pass an explicit dsn by pre-setting the
# url; otherwise resolve it here (honors TN_PG_DSN, falls back to the default).
# Either way, normalize the scheme to the psycopg 3 driver.
_url = config.get_main_option("sqlalchemy.url") or resolve_dsn()
config.set_main_option("sqlalchemy.url", _sqlalchemy_url(_url))

# No ORM models — migrations are plain DDL — so target_metadata stays None.
target_metadata = None


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table_schema=_TARGET_SCHEMA,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Pin search_path at CONNECTION establishment (libpq `options`) rather than a
    # runtime `SET` — the latter autobegins a SQLAlchemy transaction that then
    # collides with Alembic's own begin_transaction() and, worse, leaves Alembic
    # resolving alembic_version against public. As a connection option the schema
    # is a session default: the plain DDL and Alembic's version table both land in
    # the dataset's schema, and public (retail) is not on the path at all.
    connect_args = {}
    if _TARGET_SCHEMA is not None:
        connect_args = {"options": f"-csearch_path={_TARGET_SCHEMA}"}
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table_schema=_TARGET_SCHEMA,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

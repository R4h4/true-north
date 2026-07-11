"""Alembic migration environment for the governance runtime store (ADR 0010).

DSN comes from governance.pg.resolve_dsn() (honors TN_PG_DSN), never from
alembic.ini — one DSN resolver for the loader and the migrations. This module is
loaded only by Alembic at deploy time; the runtime `tn` CLI never imports it, so
SQLAlchemy stays off the per-invocation hot path.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from governance.pg import resolve_dsn

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
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

"""Initial governance runtime store: roles, users, policy_config, audit_log

Revision ID: 0001
Revises:
Create Date: 2026-07-11

The four-table schema from ADR 0010, now owned by Alembic. Raw DDL with
CREATE TABLE IF NOT EXISTS on purpose: round 1 bootstrapped these tables with
the same IF NOT EXISTS statements (governance.pg), so existing databases (our
dev DB, possibly Phong's) already have them. `alembic upgrade head` must succeed
on BOTH a fresh DB (creates the tables) and a round-1 DB (no-ops the DDL, then
stamps alembic_version to head). The DDL below is byte-identical to round 1's
bootstrap so an already-hydrated DB is left exactly as it was.
"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


_SCHEMA = """
CREATE TABLE IF NOT EXISTS roles (
    role        text PRIMARY KEY,
    definition  jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    user_id     text PRIMARY KEY,
    token       text NOT NULL UNIQUE,
    name        text NOT NULL,
    title       text NOT NULL DEFAULT '',
    role        text NOT NULL REFERENCES roles(role),
    attributes  jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS policy_config (
    key    text PRIMARY KEY,
    value  jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    ts                timestamptz NOT NULL DEFAULT now(),
    command           text NOT NULL,
    token             text,
    user_id           text REFERENCES users(user_id),
    role              text,
    request           jsonb,
    executed_query    text,
    ok                boolean NOT NULL,
    error_code        text,
    contract_version  text
);
"""

_DROP = """
DROP TABLE IF EXISTS audit_log;
DROP TABLE IF EXISTS policy_config;
DROP TABLE IF EXISTS users;
DROP TABLE IF EXISTS roles;
"""


def upgrade() -> None:
    op.execute(_SCHEMA)


def downgrade() -> None:
    op.execute(_DROP)

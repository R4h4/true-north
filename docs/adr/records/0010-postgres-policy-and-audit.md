# 0010 — Runtime policy and query audit in Postgres

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

`governance/fixtures/users.yaml` is the authored single source of policy (ADR 0007):
personas, role grants, masks, tokens, row filters. Until now the CLI read that YAML
directly on every invocation. Two things were missing for the pitch: a *runtime* policy
store separate from the authored artifact (so "how policy is authored" and "what the
running system enforces" are distinct, inspectable layers), and a query-audit trail —
who asked what, under which role, what SQL/Cypher actually ran, and whether it was
allowed.

The graph already models this split: Neo4j contents are a build artifact compiled from
authored YAML (ADR 0005), never hand-edited. We want policy to follow the same pattern.

## Decision

Add Postgres as a second compiled store alongside Neo4j.

- **Authored → runtime, same compile pattern as the graph.** `users.yaml` stays the
  source of truth. A deploy-time loader, `uv run python -m governance.pg`, is idempotent
  (upsert + prune) and hydrates Postgres. The CLI reads personas/roles from Postgres at
  runtime via `load_policy_from_db()`, which reconstructs the exact same `Policy` object
  `load_policy()` builds — a parity test pins this. Role definitions are stored as one
  JSONB `definition` column: JSONB preserves array order, and masked/tokenized grant
  order is disclosure order, so reconstruction is faithful.
- **The `users` table is the seam.** `audit_log.user_id` → `users.user_id`, and
  `users.role` → `roles.role`. Roles, users, and the audit log form one referential
  chain; the audit log cannot name a user or role the policy store doesn't know.
- **One audit row per invocation, on a deterministic CLI surface.** The CLI has a single
  emit choke point; after the envelope is built we write exactly one `audit_log` row
  (command, token, user_id/role parsed from the envelope, request params as JSONB, the
  executed SQL/Cypher, ok, error_code, contract_version, ts). Denials, invalid tokens
  (user_id NULL, attempted token stored), and the tokenless `kg schema` are all audited.
- **Fail-open audit writes.** The audit write is wrapped so any failure prints one line
  to stderr and leaves the envelope on stdout and the exit code byte-identical. Auditing
  can never change what a caller observes.
- **Unreachable policy store → clean INTERNAL envelope.** If Postgres is down, commands
  that need policy return a structured INTERNAL error ("run: docker compose up --wait &&
  uv run python -m governance.pg"), not a traceback. `kg schema` needs no policy and
  keeps working.
- **Explicitly not a contract change, and no CLI read surface for audit.** CONTRACT.md,
  the goldens, and `docs/USING-TN.md` envelope semantics are untouched; the conformance
  and e2e gates prove it. The demo reads the audit log from Postgres directly — there is
  deliberately no `tn` command that exposes audit rows.

## Consequences

The demo gains a real, inspectable audit trail and a runtime/authoring split that mirrors
the graph, reinforcing the "authored YAML compiles into build artifacts" story. Cost:
`docker compose up` now brings up Postgres too, and `make demo` runs the loader before the
smoke queries — acceptable, since compose bring-up is already required (ADR 0004/0005).
The CLI now has a Postgres dependency for every policy-bearing command; fail-open auditing
plus the INTERNAL-envelope path keep a store outage from corrupting observable behavior.

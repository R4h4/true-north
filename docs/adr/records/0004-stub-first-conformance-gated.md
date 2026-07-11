# 0004 — Stub-first delivery, conformance-gated; the stub dies at the gate

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

The harness (phase 3) and the real services (phase 4) are built in parallel by different
people on a 24-hour-class timeline. Phong could not wait for DuckDB + Neo4j to be real,
and interface drift between a mock and the real thing is the classic failure of parallel
tracks.

## Decision

Ship a pure replay stub `tn` first: same Typer entrypoint, same envelope, answers only
fixtured requests (goldens + curated agent-dev fixtures covering the trap cycles, the
persona pairs, and the self-correction error paths). One conformance suite
(`contracts/conformance/`, parametrized by `GOVERNED_CLI_CMD`) is normative for both
stub and real CLI. **When the real services pass conformance, the replay path is
deleted** — no fallback flag, no dual mode.

## Consequences

Phong's agent loop, prompts, and DoD conversations are developed against the exact
interface, and the same suite is phase 4's acceptance gate. Fixture-only PRs are a cheap
fast-lane while the stub lives. Costs accepted: un-fixtured requests return `INTERNAL`
(the stub constrains free exploration — canonical Cypher must be used verbatim), and
real-service bring-up must be one command (`make demo`) before the stub may die.

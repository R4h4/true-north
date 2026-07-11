# 0008 — Two-owner development with frontier agents; thin process, no heavy harness

- **Status:** Accepted
- **Date:** 2026-07-11

## Context

Two humans (Karsten: source/governance/knowledge-graph; Phong: harness) each drive their
own AI agents, on a hackathon timeline. The agents are frontier-class (Fable coordinating
and reviewing, Opus generating; Phong runs his own stack). Full agent-harness machinery —
enforcement loops, per-story gates, evaluator agents — exists in the AI-dev-scaffold
lineage, but measured evidence from that project says the loops intervene ~zero times at
this capability class while multiplying cost and latency. What actually fails is
*coordination between the two sides* and *drift in hand-authored artifacts*.

## Decision

Keep the process thin and put the rigor at the seams:

- `CONTRACT.md` + goldens + one conformance suite as the inter-human interface;
  interface changes only as PRs touching both.
- Every phase is a continuously-pushed **draft PR** — direction stays visible across owners.
- Deterministic validators + a pre-commit hook guard the hand-authored YAML
  (semantic layer, vocabulary, policy); cross-call invariants live in an e2e suite.
- Agents work TDD in isolated worktrees with explicit-pathspec commits; the humans (and
  Fable as coordinator) review PRs. No enforcement loops, no per-story gates, no
  evaluator agents.
- Ownership fences per tree (`harness/` vs the rest); joint files change via PR review.

## Consequences

Near-zero process overhead; the checks that exist are deterministic and fire on real
drift, not on style. We accept that agent mistakes inside a service land in the draft PR
and are caught by review/tests rather than blocked by machinery — the measured tradeoff
for this capability class. If a cheaper model ever joins the mix, revisit (the scaffold
evidence says the calculus flips somewhere below Sonnet-class).

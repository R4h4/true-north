---
phase: 1
title: "Interface Contract & Workfences"
status: pending
priority: P1
dependencies: []
---

# Phase 1: Interface Contract & Workfences

## Overview

**Superseded in substance by [PR #2](https://github.com/R4h4/true-north/pull/2)
(`contract/v0.3`, Karsten):** the contract this phase was going to draft exists —
`CONTRACT.md` (repo root, normative-only) + 10 golden examples in `contracts/examples/` +
all four services pre-registered as uv workspace members. The phase is now a **review &
ratify** exercise: Phong reviews PR #2, answers the flagged divergences, and the merge of
PR #2 is the contract freeze.

What v0.3 already covers (all of this phase's original "MUST freeze" list): CLI `tn` with
`whoami` / `metrics list|describe` / `dimensions list|describe` / `query` (flag-based DSL:
`--metric --group-by --grain --filter --start --end --limit`) / `kg schema` / `kg query`;
JSON envelope with `contract_version`, typed `applied_permissions`, per-table freshness,
provenance incl. `compiled_sql`; scalar serialization table (int VND money with 2^53
guarantee, 0–1 ratios, business-local timestamps, NaN→null); 10 error codes with
existence-vs-permission distinction (`METRIC_NOT_FOUND` + candidates vs `ACCESS_DENIED_*`
+ reason); exit codes 0/1/2; KG node labels/relationships/invariants (§4) + canonical
Cypher examples served by `tn kg schema`; 4 personas as observable behavior.

## Requirements

- Functional: PR #2 reviewed and merged with Phong's explicit positions on the flagged
  divergences; repo working agreement (ownership fences, git rules) landed in README.
- Non-functional: review turnaround same-day — this is still the only blocking sync point.

## Review positions (Phong's answers to PR #2's flagged divergences)

| Divergence | Position |
|---|---|
| 10 error codes vs draft's 4 | **Accept.** Existence-vs-permission and `did_you_mean`/`candidates` details are exactly what the agent needs to self-correct — richer is better here. |
| Exit codes 0/1/2 vs 0-always | **Accept 0/1/2.** Machine-distinguishable handled-error vs crash is conformance-testable; harness treats "non-zero without parseable envelope" as `INTERNAL` per contract. |
| 4 personas, region-scoped (South) row filter | **Accept.** `marketing_ops` makes masked/tokenized/banded separately demoable; region beats city for row-filter visuals. |
| `CONTRACT.md` root + `governance/fixtures/users.yaml` vs `docs/…` + `contracts/personas.json` | **Accept.** Locations are Karsten's tree; only tokens + observable behavior are contract. |
| CLI name `tn` | Accept. |

To confirm in the same review (genuinely open, not in the PR body):

1. **Stub ownership** — CONTRACT.md says "a stub with canned responses ships first; same
   contract, same goldens" under the `tn` entrypoint. Recommend: Karsten ships the stub
   (it lives in his tree under `tn`); Phong owns the conformance runner and contributes
   replay fixtures for extra demo questions (see phase 2).
2. **`ROW_LIMIT` / `STALE_DATA` warning codes** — closed set or open? (Harness narrates
   warnings; an open set means narrate generically.)

## Related Code Files

- Review (Karsten's PR): `CONTRACT.md`, `contracts/examples/*.json`,
  `governance/fixtures/users.yaml`, root `pyproject.toml` + placeholder packages.
- Modify (after merge, Phong): `README.md` — ownership table + git rules from plan.md
  "Parallel-Work Rules"; point the interface-spec line at `CONTRACT.md`.

## Implementation Steps

1. Phong reviews PR #2 against this phase's checklist; posts the positions table above
   plus the two open questions as the review.
2. Merge PR #2 (Karsten merges after discussion resolves; contract v0.3 = frozen v1).
3. Phong lands README ownership/workflow section (small follow-up PR or direct push after
   merge — it touches a joint-controlled file, so PR if any wording is contested).
4. Rebase/re-point anything in flight: `plans/` PR #1 references updated (done in this
   plan), harness env defaults set to `uv run tn`.

## Success Criteria

- [ ] PR #2 merged with the divergence positions recorded in review comments.
- [ ] Stub ownership + warning-code question answered in the review thread.
- [ ] README documents ownership fences, push-to-main + rebase rule, joint-controlled
  paths (`CONTRACT.md`, `contracts/examples/`, root `pyproject.toml`, `README.md`), and
  the `uv.lock` regen rule.
- [ ] Both tracks can state "what I build next" without asking the other anything.

## Risk Assessment

- **Review scope creep** (re-litigating v0.3 details) → the contract is demonstrably
  better than the draft; only the two open questions block. Everything else is a
  changelog entry later, per the contract's own PR rule.
- **README rules slip** → they're the anti-collision agreement; land them the same day
  even if as one commit.

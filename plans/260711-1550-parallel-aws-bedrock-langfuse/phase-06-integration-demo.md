---
phase: 6
title: "Integration & Demo"
status: pending
priority: P1
dependencies: [3, 4, 5]
---

# Phase 6: Integration & Demo

## Overview

Joint final phase: point the harness at the real governed CLI, prove nothing broke
(conformance + trap evals), and script the demo. Hard-blocked by the full-scale dataset
from plan `260711-1547-phongvu-demo-data`.

## Requirements

- Functional: harness answers the 8 TRAPS.md questions correctly through the real stack,
  per persona; KG-sourced "you lack access" answer works live.
- Non-functional: runs entirely on the EC2 box; demo repeatable from a clean
  `docker compose up`; Langfuse traces reviewable live as the "observability" part of the
  pitch.

## Architecture

No new components. The stub is replaced by the real `tn` behind the same entrypoint
(`uv run tn`) — the harness config doesn't even change. Everything that differs beyond
that is a bug in the contract, the stub fixtures, or the real CLI — triaged by running
the conformance suite against both.

## Related Code Files

- Modify: `harness/.env.example` / EC2 env (CLI swap), `harness/agent/system_prompt.py`
  (tuning against real KG/graph shapes).
- Create: `docs/demo-script.md` (personas, questions, expected beats, reset instructions),
  `harness/evals/trap_questions.py` (the 8 questions + per-persona expected properties —
  lightweight asserts, not a framework).

## Implementation Steps

1. On the EC2 box: generate full-scale data (per demo-data plan), run KG ingest, start stack.
2. Run conformance suite against real CLI; fix contract-level breaks first (joint).
3. Run the 8 trap questions × `tok-exec-mai`; compare against
   `source/data/validation_report.md` values (from the demo-data plan) — the agent's
   numbers must match the "correct" query column, not the naive one.
4. Persona pass: same headline question for all 3 tokens; verify row filtering, masking
   notices, and the KG "metric exists, access denied" beat.
5. Prompt tuning iterations (expect a few) — each eval run visible in Langfuse; use trace
   comparison to show improvement in the pitch.
6. Write `docs/demo-script.md`; dry-run the full demo once from instance stop/start.

## Success Criteria

- [ ] Conformance suite green against the real CLI on the EC2 box.
- [ ] ≥6 of 8 trap questions answered with the correct (non-naive) number + caveat named;
  the remaining ones fail gracefully with honest uncertainty (never a confident wrong number).
- [ ] Persona demo beats reproduce on two consecutive dry-runs.
- [ ] Demo script committed; a teammate can run the demo without the author.

## Risk Assessment

- **Real CLI late** (Phase 4 slip) → demo on the stub (Phase 2 fixtures) with a
  "governance layer in progress" slide; decided at the day-5 checkpoint, not demo
  morning. Be honest about the limits of this fallback: canned responses won't survive
  judge follow-up questions, so on the stub, script the demo tightly and say what's
  canned.
- **Agent regresses on real Cypher schema** (fixtures were canned) → budget half a day of
  prompt tuning; keep stub-era traces in Langfuse for A/B comparison.
- **Full-scale data too slow on the box** → fall back to `--scale small` for the live
  demo; traps hold at all scales (per demo-data plan), so the story survives.

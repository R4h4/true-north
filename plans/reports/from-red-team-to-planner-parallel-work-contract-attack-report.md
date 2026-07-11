# Red-Team Attack Report: Parallel-Work Contract Plan

Plan: `plans/260711-1550-parallel-aws-bedrock-langfuse/` (plan.md + phases 1–6)
Reviewer stance: adversarial, evidence-based. 12 findings, ranked.

---

## 1. CRITICAL — The KG Cypher dialect/schema is not in the contract, and the mock is designed to hide that

**Evidence:** Phase 1 contract covers commands, envelope, error codes, personas — nothing about node labels, relationship types, or property names of the knowledge graph. Phase 4 explicitly says KG internals are "his to design." Phase 2 architecture: *"Unknown Cypher → a generic 'no results' success, not an error."* Phase 3: the **LLM writes the Cypher** live.

**Attack:** Phong tunes the agent's Cypher-generation (system prompt, tool description, few-shot examples) for weeks against fixture patterns he invented. Karsten independently designs the real graph schema. At Phase 6, every LLM-generated Cypher query returns empty against the real graph — and because the contract says empty ≠ error, nothing fails loudly. The conformance suite only replays golden examples; it never tests the LLM's live Cypher. Phase 6's risk note ("budget half a day of prompt tuning") massively underprices this: it's not tuning, it's the agent's entire graph vocabulary being wrong. Real Neo4j also throws syntax errors (`INVALID_QUERY`) on malformed Cypher — a path the mock never exercises because it never rejects anything.

**Fix:** Put the KG schema in the frozen contract: the labels, relationship types, and property names for metric / dimension / caveat / persona-access nodes (half a page, e.g. `(:Metric {name, definition})-[:HAS_CAVEAT]->(:Caveat)`, `(:Persona)-[:CAN_ACCESS]->(:Metric)`). Mock fixtures must implement exactly that shape. Add one `INVALID_QUERY` golden example for the `graph` surface and make the mock reject syntactically garbage input. This is the single highest-leverage half-hour of the Phase 1 session.

---

## 2. CRITICAL — The mock imports `source/query/engine.py`: a cross-fence dependency on un-frozen internals that Phase 4 will break by design

**Evidence:** Phase 2 architecture: *"delegate to the existing read-only DuckDB engine (`source/query/engine.py`, imported read-only — no edits to Karsten's files)."* Plan rule 1: *"Directory ownership is absolute."* Phase 4 step 2: Karsten builds the governance engine *"wrapping the existing read-only query engine"* — i.e. he will refactor exactly this module, in his own directory, without needing anyone's permission.

**Attack:** "Read-only import" is still a hard code dependency. The joint-controlled list (contract doc, `contracts/`, README, root pyproject) does not include `source/query/engine.py`, so the mock's most load-bearing dependency sits on code the fence rules explicitly let Karsten rewrite at will. First rename of `connect()`/`run_query()` or move to `source/semantic/` breaks Phong's mock — and with it the conformance suite and all of Phase 3 dev — mid-parallel-work, with no rule violated by anyone. Secondary problems: `harness` must declare a workspace dep on the `source` package (packaging not addressed), and the engine reads gitignored `source/data/parquet/`, so mock behavior depends on each laptop's locally generated data.

**Fix (pick one, in preference order):** (a) The mock owns a ~20-line DuckDB reader over `source/data/parquet/` — data files are a stable contract, code internals are not; (b) add `source/query/engine.py`'s public functions (`connect`, `run_query`, `QueryError`) to the frozen joint-controlled surface in the contract doc; (c) at minimum, list the import in the contract so the coupling is a named decision, not an accident.

---

## 3. MAJOR — "Raw SQL vs DSL" deferral is not absorbed by opaque strings: the LLM is the query author

**Evidence:** Phase 1 risk: *"harness treats query strings opaquely either way, so it absorbs this without code change."* Phase 3: the tool specs, system prompt, and TRAPS-aware prompting all teach the model to write queries.

**Attack:** The plumbing is opaque; the agent is not. A prompt that teaches the model DuckDB SQL against the star schema (tables, join keys, `channel <> 'b2b'` idioms) is a completely different artifact from one that teaches a metrics DSL (plus the proposed extra `metrics`/`dimensions` discovery subcommand, which changes the tool count). If Karsten picks DSL on day 3, Phong's Phase 3 prompt/tool work is rework, not a config change. The plan sells this as absorbed risk; it's deferred rework on the critical path.

**Fix:** Decide in Phase 1, for real: contract v0 = raw SQL passthrough, DSL explicitly out of demo scope (a v1 changelog entry that ships only if there's slack). If Karsten wants DSL, the grammar freezes day 0 with the rest of the contract.

---

## 4. MAJOR — Envelope ambiguities the conformance suite cannot catch

**Evidence:** Phase 1 spec: *"JSON envelope on stdout, exit code 0/1, logs to stderr"* plus two example envelopes.

**Attack — three concrete divergence points:**
- **Exit-code semantics undefined.** Is `PERMISSION_DENIED` exit 0 (envelope delivered) or exit 1? If mock and real CLI disagree, the harness tool dispatcher branches on the wrong signal (e.g. treats a clean denial as a crash, or swallows a crash as a denial). Golden examples may not pin exit codes at all if the suite only diffs stdout.
- **Value serialization unspecified.** DuckDB yields `Decimal`, `date`, `datetime`, `NULL`. ISO strings? Floats? `null`? Mock (raw engine) and real CLI (Karsten's stack) will serialize differently on any type the golden examples don't happen to cover.
- **`graph` data shape unspecified.** The `columns/rows` example is warehouse-shaped; Cypher returns maps, nodes, and paths. How does a node serialize? Unpinned = mock invents one shape, real CLI another, and the agent's result-parsing prompt was tuned on the wrong one.

**Fix:** One paragraph each in the contract: exit 0 iff a JSON envelope was written (even `ok:false`), nonzero only for catastrophic failure; dates as ISO-8601 strings, amounts as int64, nulls as `null`; `graph` results flattened to the same `columns/rows` shape with scalars only. Add a conformance invariant test for each (not just golden diffs).

---

## 5. MAJOR — Value-asserting golden examples break the moment dataset scale changes

**Evidence:** Phase 1: golden request/response pairs with concrete rows. Phase 2: conformance asserts golden examples. Phase 6 step 1: EC2 runs **full-scale** data; step 2 runs the conformance suite there. Phase 4 step 5: Karsten tests on tiny/small.

**Attack:** A golden `query` response containing actual row values is only valid for one `(scale, seed)` pair. The suite goes green on laptops (tiny, seed 42) and red on the EC2 box (full) — during Phase 6, the worst possible time — and the failure looks like a governance bug, burning joint debugging hours on a fixture artifact.

**Fix:** Conformance suite pins `--scale tiny --seed 42` as a documented precondition (and the EC2 run regenerates tiny data just for the suite), or goldens assert structure + invariants (columns, row-count relations between personas, error codes, notice presence) rather than cell values. Say which, in the contract.

---

## 6. MAJOR — First real harness↔real-CLI contact is effectively day 5; the mid-point checkpoint is a passive checkbox

**Evidence:** Dependency graph in plan.md: tracks join only at Phase 6. Phase 4 success criteria mention *"Checkpoint sync with Phong at: conformance-green (mid), KG-populated (late)"* — but no phase schedules it, no acceptance criterion enforces it, and Phase 6 is explicitly the swap point.

**Attack:** All contract holes above (Cypher schema, serialization, exit codes) surface simultaneously on day 5–6, on a remote EC2 box, under demo pressure. Conformance-green is necessary but not sufficient — it proves golden-example equivalence, not that the live agent works against the real stack.

**Fix:** Make it a hard gate: the day Karsten's CLI first passes conformance (target day 2–3), Phong runs the full harness against it locally for one hour and files every mismatch as a contract-changelog item. One line in Phase 4's success criteria upgraded from "sync" to "harness smoke-tested against real CLI, mismatches triaged."

---

## 7. MAJOR — Governance semantics ("masked") are undefined; mock shim and real engine will implement them differently

**Evidence:** Phase 1 persona table: CEO *"full rows, PII masked"*; analyst *"no PII columns"*. Phase 2 shim: *"column masking (PII for tok_analyst/tok_ceo → notices)"* — note the shim already conflates the two personas the contract distinguishes. `notices` are free-form prose.

**Attack:** "Masked" can mean value replaced (`***`), tokenized, nulled, or column dropped. "No PII columns" vs "PII masked" are different mechanisms per the contract table, yet the mock plan treats them identically. The real engine (README: *"column-level anonymization, PII tokenization"*) will pick differently. Conformance can't strictly assert free-text notices, so this divergence sails through green — and the agent's answer phrasing (which surfaces notices verbatim per Phase 3) changes behavior between mock and real.

**Fix:** Contract defines exactly: masked = value replaced with a fixed sentinel + machine-readable notice (e.g. `{"type": "column_masked", "column": "customer_name"}` instead of prose); denied column = absent from result + notice. Conformance asserts notice *structure*, prose is display-only.

---

## 8. MAJOR — Joint-change control on root `pyproject.toml` and the conformance suite creates day-1 mutual blocking and an ownership contradiction

**Evidence:** Plan rule 2 puts `contracts/` and root `pyproject.toml` behind cross-approved PRs. Phase 2 (Phong, day 1) must modify root pyproject (add `harness`) and author `contracts/conformance/` solo. Karsten must add `governance`/`knowledge-graph` members too. Verified: root pyproject currently has `members = ["source"]` only.

**Attack:** Day 1, both people need root-pyproject PRs approved by each other before either can scaffold — the exact serialization the plan exists to avoid. Worse: the conformance suite is joint-controlled, but Phong writes it while iterating on his own mock; every golden/test tweak during Phase 2 legally requires Karsten's PR review. Under hackathon pressure this gets bypassed, and once one fence rule is bypassed, all of them are theater. Plus shared root `uv.lock` conflicts on every dep add from either side (the `uv lock` rule helps merge them but the plan underestimates frequency).

**Fix:** In the Phase 1 joint session, commit root pyproject once with **all four** workspace members pre-added — it never needs touching again. Scope joint control to `docs/governed-cli-contract.md` + `contracts/examples/` + `contracts/personas.json`; the conformance test *implementation* is Phong-owned with a single Karsten sign-off at Phase 2 exit. Allow async chat-"LGTM" as PR approval.

---

## 9. MINOR — CODEOWNERS + branch protection is incompatible with the direct-push-to-main workflow, and is process theater for 2 people

**Evidence:** Plan rule 3: *"small commits straight to main."* Phase 1 step 5: branch protection via CODEOWNERS on joint paths.

**Attack:** GitHub cannot require review per-path while allowing direct pushes: CODEOWNERS only gates PRs, and direct pushes to main bypass it entirely — so the setting either does nothing (pushes bypass) or, if you block direct pushes, both people are stuck making PRs for every commit, contradicting rule 3. Either way, 10 minutes spent installing a control that misleads. YAGNI for a 2-person team whose actual enforcement is `git log --stat` + trust (already in acceptance criteria).

**Fix:** Delete Phase 1 step 5.

---

## 10. MINOR — The "mock as fallback demo" path is weaker than the plan claims and has an unplanned deployment coupling

**Evidence:** Phase 4 risk: *"Phase 2 mock IS the fallback demo path."* Plan acceptance criterion: KG-permission-metadata answer sourced from the graph. Phase 5 architecture wires the harness container to the real CLI only; Phase 2's mock needs the `source` package + generated parquet inside whatever container runs it (see finding 2).

**Attack:** In fallback mode the "KG permission metadata" beat is a canned string-match — demoing vaporware; one judge question ("show me the graph") collapses it. And nothing in Phase 5 plans a mock-mode compose profile: the harness image must then bundle `source/` code + data, a cross-ownership build coupling nobody scheduled.

**Fix:** Acknowledge the fallback demo demotes the KG beat to "in progress" honestly (the plan's Phase 6 note does; Phase 4's "IS the fallback" oversells it). Add one line to Phase 5: harness image includes mock + tiny dataset so `GOVERNED_CLI_CMD` swap works on the box in both directions.

---

## 11. MINOR — Timeline anchors on an unknown deadline, and day-1 Bedrock success is outside the team's control

**Evidence:** plan.md open question 2 admits the demo date is unknown while every phase is day-numbered. Phase 5A success criterion: converse call working *"by end of day 1"*; risk note admits Anthropic use-case approval can delay it (mitigation: fake converse fixtures — adequate for Phase 3, but Phase 1/2 sequencing already assumes ~1 week).

**Attack:** If the hackathon is 3 days, the plan's core bet (a full mock + conformance layer before any agent code) may itself be the over-investment; if it's 2 weeks, the single Phase 6 integration point is even less defensible. A plan that can't state its deadline can't defend its sequencing.

**Fix:** Resolve open question 2 before Phase 1, and write the compressed variant now (which phases merge if ≤3 days: mock shrinks to personas + canned envelopes, conformance shrinks to golden-diff script).

---

## 12. MINOR — Phase 1 half-day scope is achievable only if the defaults are actually enforced

**Evidence:** Phase 1 wants, in ~3h: frozen 2-page spec, personas fixture, ≥6 golden examples, README ownership section, branch protection — while also resolving SQL-vs-DSL (finding 3) and, per this report, KG schema (finding 1), serialization/exit codes (finding 4), and masking semantics (finding 7).

**Attack:** The added contract items are exactly the ones that prevent day-5 blowups, but they inflate the timebox. The "silence = accepted" default is good; it just doesn't currently cover the questions that matter.

**Fix:** Extend the pre-written defaults so the session ratifies rather than designs: default KG schema sketch, default exit-code rule, default serialization rules, default mask semantics — all drafted before the session (1–2h of Phong's day-0 morning), Karsten edits rather than invents. Golden examples can land as a fast-follow same-day commit rather than in-session.

---

## Ranked summary

| # | Severity | Finding |
|---|---|---|
| 1 | Critical | KG Cypher schema absent from contract; mock's "unknown Cypher → empty success" masks the divergence until day 5 |
| 2 | Critical | Mock imports `source/query/engine.py` — cross-fence dependency on internals Phase 4 will refactor |
| 3 | Major | SQL-vs-DSL deferral: the LLM authors queries, so the prompt/tool specs are not "opaque" |
| 4 | Major | Exit-code, value-serialization, and graph-result-shape ambiguities conformance won't catch |
| 5 | Major | Value-asserting goldens break on dataset scale change (tiny laptop vs full EC2) |
| 6 | Major | Mid-point harness↔real-CLI integration is an unscheduled checkbox; real contact is day 5 |
| 7 | Major | "Masked" semantics undefined; free-form notices untestable; shim already conflates persona behaviors |
| 8 | Major | Joint control on root pyproject + Phong-authored conformance = day-1 mutual blocking + ownership contradiction |
| 9 | Minor | CODEOWNERS/branch protection incompatible with push-to-main; process theater for 2 people |
| 10 | Minor | Mock-fallback demo oversold; mock-mode EC2 deployment coupling unplanned |
| 11 | Minor | Day numbering rests on unknown deadline; day-1 Bedrock gate outside team control |
| 12 | Minor | Phase 1 timebox holds only if defaults are pre-drafted to cover findings 1/3/4/7 |

Findings 1, 2, 4, 7, and 12 are all fixable inside the existing Phase 1 session by pre-drafting contract text — no new phases needed. Findings 6 and 8 are one-line edits to Phase 4/Phase 1. The plan's core strategy (contract + mock + conformance) is sound for the timeline it assumes; the holes are in what the contract omits and in the one cross-fence import it self-authorizes.

# Tasks 002: offline quality evaluation

**Status:** product contract prepared. Rules and format are prepared; implementation, corpus candidates and human labels remain pending. Task and issue links record accepted results rather than predictions.
**Sources:** [specification](spec.md), [plan](plan.md), [rules](rules.md), [format](corpus-format.md).

## 1. Execution and ownership

This file owns E01-E16 and their dependencies. Q1-Q18 remain requirement IDs; E does not continue prototype T1-T11. An implementation issue is one bounded contract and one PR. The implementation author remains OpenCode / GLM-5.3 and the reviewer Codex. The lead writes acceptance tests before dispatch; humans confirm reference labels. An agent's draft label never becomes human confirmation through technical approval.

The public contract and acceptance tests are owner-authored deliveries under AGENTS.md Boundaries. An implementation author changes only the paths named in its issue, plus the existing acceptance xfail exception. No new dependencies, paid product-model calls or independent product blocks follow automatically from this list. Every PR runs all six Commands and names the distinct defect behind each new test.

The holdout custodian does not implement or tune rules. Before freezing, the author and code reviewer see development material only; hidden cases, labels and access evidence do not enter their inputs, CI or public artifacts. Publication after independent measurement is a separate decision and removes blind status for future tuning.

## 2. Dependencies and state

| ID | Stage | Result | Depends on | State |
|---|---|---|---|---|
| E01 | 1 | Finite parsing contract | Approved technical plan | Contract prepared |
| E02 | 1 | Document format and source annotations | E01 | Format prepared; annotations agent-prepared |
| E03 | 1 | Forty development and twenty held-out candidates | E01, E02 | Pending; human labels absent |
| E04 | 1 | Schemas and verified package loading | E02, published contract | Pending; two implementation units |
| E05 | 1 | Approved input gate for the evaluator | E01-E04 | Not passed |
| E06 | 2 | Verified typed fact index | E05 | Pending |
| E07 | 2 | Number, price and form parsing | E06 | Pending |
| E08 | 2 | Other constructions and full text coverage | E07 | Pending |
| E09 | 2 | Obligations and aggregate verdict | E08 | Pending |
| E10 | 3 | Metrics and independent result axes | E09 | Pending |
| E11 | 3 | Consistent JSON/Markdown | E10 | Pending |
| E12 | 3 | Offline CLI and safe report writes | E11 | Pending |
| E13 | 3 | Integrated compatibility verification | E12 | Pending |
| E14 | 4 | Frozen acceptance candidate | E03, E13 | Pending |
| E15 | 4 | One independent twenty-case run | E14 | Pending |
| E16 | 4 | Evidence and delivery decision | E15 | Pending |

E03 and E04 can proceed in parallel. The first E04 unit uses format examples, not a requirement to finish all sixty. E04 is accepted only after both document loading and complete package validation/projection are verified. E05 remains a separate human/reference gate before E06-E09.

## 3. Stage 1: contract and data

### E01. Finite rules

Requirements: Q5, Q7-Q10, A3-A6. Scope: rules.md; no generator change.

Every construction has an ID, type, boundaries, normalisation, source and close positive/negative or unsupported example with an outcome. Equal prices are allowed; batch capacity is distinct from object mass; unresolved source roles stay unresolved. Examples are disclosed development material. The result is a reviewed rule contract, not a parser or human-labelled corpus.

### E02. Format and source annotations

Requirements: Q1-Q3, Q5-Q6, Q13, Q16. Scope: corpus-format.md, schema, sources/facts and format examples.

Define required fields/types/enums/nulls, IDs, hashes, observations, provenance, labels and safe failure behaviour. Annotate all nine public products with verified source spans, separately from answers. Specify evaluator-visible fields. Provide valid and intentionally malformed examples, including an identical duplicate key. The published schema/format must let an E04 author implement without guessing.

### E03. Candidate corpus and human review

Requirements: Q1-Q5, Q16-Q17, A1-A2. Scope: public development preparation and separately controlled holdout.

Prepare sixty candidates, thirty per language, forty development/twenty holdout and the five-family paired matrix. Groups include common originals, mutations and translations and never cross partitions. Fix question obligations before answers and preserve all provenance. Agent proposals start pending. E03 produces honest candidates, not automatic human certification. Human development labels are confirmed in E05; holdout labels before E14.

Before E14 the holdout has ten correct and ten incorrect, ten per language, with no unresolved references. Previously disclosed specification/rule/probe/T11 examples are not holdout. Insufficient independent groups means incomplete preparation, not relabelling relatives or changing counts.

### E04. Schemas and package loading

Requirements: Q1-Q3, Q6, Q11, Q13, A1, A7-A8. Scope: quality_schema.py, quality_corpus.py and distinct unit tests; owner acceptance tests are supplied separately.

Deliver two bounded implementation issues/PRs:

1. Strict closed models and asynchronous single-document decoding. Detect nested duplicates before dictionaries/models, reject non-finite constants and lexical type coercion, preserve text/null, pair parsed content with the raw-byte hash and provide safe typed read/decoding/structural errors. No provider or app startup.
2. Full package checks of sources, bindings, question hashes, IDs/references/lineage/groups, exact evidence and typed fact/support consistency, cross-field observation/label invariants and the isolated assessment projection. Source-path safety and atomic invalid-package failure are required. Validate supplied partitions without requesting hidden twenty; the custodian validates combined readiness.

Both units are needed for E04 acceptance. Valid recorded failures remain observations; unknown upsell IDs are not filtered out before factual evaluation. The assessment input excludes labels, categories, case/group IDs, partition, provenance and filenames. Bad input cannot become an empty successful package.

Distinguishing defects: silently ignored nested field, duplicate key/ID overwritten, normalised rather than raw-byte hash, changed source accepted, wrong source span/value/role, lost or invented directed edge, leaked label in projection, swallowed read failure and blocking file I/O.

### E05. Gate before parser implementation

Requirements: Q2-Q5, Q7, Q16. Scope: real confirmations and pinned versions, not new code.

Require approved rules/format, actual human-confirmed development references, fixed source/fact/rule revisions, the published author-accessible contract and accepted complete E04. Until then E06-E09 do not start. Planning approval or agent preparation does not pass this gate.

## 4. Stage 2: deterministic evaluator

### E06. Typed source facts

Requirements: Q6-Q8, A3-A5. Scope: quality_facts.py and its tests.

Verify evidence and produce Decimal/currency and distinct quantity/unit/size/role types. Preserve unresolved components rather than inferring absent mass. Work from annotations without product-ID branches or human answer labels. Reject unsupported/inconsistent annotation as invalid input.

Distinguishing defects: float hides a cent, `02` loses its zero, a neighbour's form is borrowed, batch quantity becomes device mass, wrong evidence is accepted.

### E07. Price and form rules

Requirements: Q7-Q9, A3-A5. Scope: N normalisation and R01-R03/F01-F08 in quality_rules.py.

Implement only approved complete constructions, bounds and original-offset mapping. Correct declared paraphrases pass; invalid grouping is not collapsed, wrong supported quantities/units are errors and protected context is not mined for positive claims. Correct price cannot consume an unknown next claim.

Distinguishing defects: quoted price extracted, all spaces deleted, foreign nearest subject selected, report span shifted by normalisation.

### E08. Other rules and uncovered text

Requirements: Q7-Q10, A4-A6. Scope: remaining R rules and coverage of both fields.

Handle declared descriptions, batch/size, directed relations, stock/delivery, absence phrases and service text. Preserve every unsupported fragment. Do not inherit subjects across fields/sentences. A known upsell ID does not certify its hint.

Distinguishing defects: delivery accepted from kb_match, role ambiguity erased, extra property discarded, inverse edge invented, hint ignored.

### E09. Obligations and aggregation

Requirements: Q8-Q12, A5-A7, A10. Scope: M/A rules and integration.

Error outranks uncertainty only with established grounds; keep unchecked details. Confirmed requires full coverage and obligations. Equal repeats are permitted, wrong values have their own grounds. Distinguish proven omission from unsupported paraphrase. Preserve existing product/stem checks and stage-specific disclaimer policy. Metadata changes cannot alter factual assessment.

Distinguishing defects: correct price hides wrong price, equal prices falsely rejected, unknown tail confirmed, human label consulted, model_output incorrectly required to carry final disclaimer.

## 5. Stage 3: metrics, reports and CLI

### E10. Metrics and readiness

Requirements: Q11, Q14-Q18, A7, A9, A11. Scope: quality_report.py calculations.

Use exact E/C/W sets and denominators, null for zero, explicit failures/label uncertainty and the complete fixed twenty acceptance set. Verify truth/language balance, human confirmation, completed evaluation and independence. Preserve 0/0/4; a fifth manual case fails. Synthetic factual errors are not execution failures.

Distinguishing defects: failure lowers an error rate, unresolved counts as correct, empty set passes, 5/20 accepted, model/evaluator quality mixed.

### E11. Consistent reports

Requirements: Q1, Q13-Q14, Q17-Q18, A9, A11-A12. Scope: JSON/Markdown renderers.

Use one result model, report_kind=quality-evaluation/schema_version=1, stable order and reproducible content. Include full source/question/answer, evidence/reasons/spans, label state and every summary group with links to cases. Keep answer-set status distinct from evaluator acceptance. Inspect actual outgoing reports for restricted content.

Distinguishing defects: Markdown success contradicts JSON, missing reason/group, lost source or rules version.

### E12. Offline command and safe publication

Requirements: Q6, Q11, Q13, Q18, A7-A8, A11-A12. Scope: evaluate_quality.py, real subprocess tests and report writing.

Implement explicit replay/acceptance and 0/1/2 semantics, without provider settings/client/startup/network. Empty input is unsuccessful. File writes are off-loop, use a new directory and protect inputs/historical outputs and aliases. Success requires both reports; errors are safe and cannot leave a partial pair advertised as final.

Distinguishing defects: absent entry point, success without report, failed second write masked, input overwritten by alias, blocking write.

### E13. Integrated compatibility

Requirements: Q12, Q18, A10-A12. Scope: verified integrated commit and existing tests/evidence; another PR only for a discovered in-scope fix.

Confirm API, generator, YAML, old live command and binary passed keep their behaviour. Run all six Commands on the candidate, with distinct defects behind new tests and real CLI outcomes. This is neither independent holdout acceptance nor justification for redundant decorative tests.

## 6. Stage 4: independent acceptance and delivery

### E14. Freeze

Requirements: Q1-Q5, Q16-Q17, A1-A2, A9. Pin accepted code, both sources, rules, annotations, corpus, labels and access evidence. The custodian verifies disjoint groups and no prior disclosure to tuning/implementation. All twenty are human-confirmed definite 10/10 truth and 10/10 language. Contaminated data is not_ready, not almost independent.

### E15. One independent offline run

Requirements: Q6, Q13-Q18, A8-A9. Evaluate all fixed twenty without product calls. Measure evaluator errors against human truth and honestly retain pass/fail/not_ready under 0/0/4. Do not drop cases, change rules during the run or turn repeated tuning into a new independent measurement. Completing the task does not guarantee pass.

### E16. Evidence and next decision

Requirements: Q13-Q18, A11-A12. Retain original reports, revisions and case reasons, with actual bounded claims. After fail, distinguish a fix/regression from a newly agreed independent set. Inspect and approve any public delivery separately; it does not authorize new live product-model runs.

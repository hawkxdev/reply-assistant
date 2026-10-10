# Technical plan 002: offline answer quality evaluation

**Status:** architecture and verification contract for the implemented offline evaluator. Implementation, corpus and historical acceptance evidence are tracked only in [tasks.md](tasks.md).
**Contract:** [specification](spec.md), Q1-Q18 and A1-A12; [finite assessment rules](rules.md); [corpus format](corpus-format.md).

## 1. Result and boundaries

Build a reproducible assessment of recorded answers against a pinned public knowledge base, then measure the evaluator against human reference labels. Generation, `/api/suggest`, prompts, service checks, catalogue YAML, retry/fallback behaviour and the historical live T11 evaluator keep their existing contracts. No new dependencies, judge model, product-model calls, network or key are needed.

The first version supports the declared EN/RU grammar. Unsupported constructions, ambiguous bindings and uncovered content require manual review. Zero false confirmations, zero false rejections and at most four manual cases out of twenty are acceptance requirements, not properties already established for this design.

Each case includes its question, full customer reply and manager hint, source version, observation stage and provenance. Public examples use only the two fictional catalogues. Recorded answers remain verbatim; the corpus does not store working customer conversations. Synthetic mistakes test the evaluator, not the product model's error frequency.

## 2. Architecture

### Offline boundary

The new evaluator does not call `evaluation.evaluate()`, `service.suggest()` or a provider client. Loading imports no application startup and requires no provider settings. Reuse existing knowledge-base validation and pure product/forbidden-stem checks without changing their behaviour. File I/O runs outside the event loop through `asyncio.to_thread`; small pure comparisons remain synchronous.

The pipeline is: decode and verify a package -> build an assessment-only projection -> parse and compare facts -> aggregate a factual verdict -> compare with human labels -> render reports. Invalid input stops the package before assessment. Label comparison is a separate operation after the automatic verdict exists.

### Data and authority

| Entity | Contents | Visible to factual assessment |
|---|---|---|
| Sources | Catalogue paths, raw-byte SHA-256, language, rule policy and hash | Verified catalogue and applicable rules |
| Facts | Source-wide product annotations, typed values, support states, exact evidence spans | Yes, after source verification |
| Question obligations | Required subjects/predicates/actions by field and allowed `kb_match` | Yes, fixed before the answer |
| Observation | Original four answer fields, stage or recorded execution failure | Yes |
| Provenance | Question/answer origin, original artifact and known generation parameters | No; reports only |
| Human label | Status, proposed and actual verdict, rationale, source evidence and confirmation | No; metrics and reports only |
| Corpus metadata | Case/group IDs, partition, categories and filenames | No; organisation and summaries only |

Use strict closed Pydantic models after standard JSON decoding. Detect duplicate keys before dictionaries/models; JSON structure does not prove factual truth. The schema and semantic format are separate owners. Fact annotations apply to the source, not a particular expected answer; they do not alter YAML or contain permitted full replies. Hash or evidence mismatches are input failures, never model factual errors.

The evaluator receives only a verified source, product facts, question obligations without `id`/`basis`, and the observation. It cannot access labels, case/group identifiers, categories, origins, partitions or file metadata through arguments, globals or filesystem reads. Changing those forbidden metadata fields while permitted content stays equal must not change a factual verdict.

### Parsing and complete text accounting

[rules.md](rules.md) is the complete grammar, not a set of substrings to search anywhere. The forbidden-stem checks run on both original fields first. N07 scans each whole field for quoted, conditional, negative, comparative or interrogative context before segmentation. Only the explicitly bounded R11/R12/R15 exceptions are masked, in the declared order. Protected context requires manual review; it cannot create positive facts from a matched prefix.

For an unprotected field, parse complete constructions with explicit subjects and preserve Unicode code-point spans in the original string. Normalisation keeps a mapping to original offsets. R03 is the only supported shared subject between clauses; pronouns, nearest-name guessing and cross-sentence/field inheritance are unsupported. Unknown tails remain unchecked content rather than being swallowed by a recognised prefix. Ambiguous parses are not resolved by choosing the first match.

Every character of both fields belongs to a checked claim, recognised service phrase, permitted separator or unchecked remainder. A correct price does not cover another claim, a contradiction or the hint. A missing required fact is an established completeness error only after all relevant text is resolved; a possible unknown paraphrase requires manual review.

Prices use `Decimal` from the normalised string, with explicit USD/RUB and no float, rounding or conversion. N02 fixes decimal and thousands separators; `3 900` can be valid while `3 9 00` is unsupported. Units remain typed: package quantity, form quantity, portion mass, batch capacity, section count and filter-size code are distinct. `02` keeps its leading zero. The spoon's `5 g` has unresolved role; the grinder's `30 г за раз` is batch capacity. Do not infer object mass from either a package quantity or an unresolved form component.

Equal repeated prices, including `18.00` and `18,00`, are not errors. When `18.00 USD` and `99.00 USD` are separately established for the same powder, only the wrong value contributes a price error; both spans remain visible. A price under a protected condition or quote is not established by token matching. Grammar extension is a contract change with close positive/negative examples, never a case-ID exception during acceptance.

### Results and failure axes

| Axis | Values | Meaning |
|---|---|---|
| `execution_status` | `evaluated`, `recorded_failure`, `invalid_input`, `evaluator_error` | Execution independently of answer content |
| `factual_verdict` | `confirmed`, `error`, `manual_review`, null | Null when no answer was assessed |
| `human_status` | `pending`, `confirmed`, `disputed` | Reference provenance |
| `human_verdict` | `correct`, `incorrect`, `unresolved` | Human assessment of full content |
| `answer_set_status` | `all_confirmed`, `has_errors`, `needs_review`, `incomplete` | Quality of recorded answers |
| `evaluator_gate` | `pass`, `fail`, `not_ready` | Evaluator acceptance |

A proven factual, metadata or domain violation outranks uncertainty; preserve uncertainty in the details. Without a proven violation, any unresolved mandatory fragment excludes `confirmed`. `upsell_product_id` and `kb_match` are claims to check, not reference truth. Existing service rejection without a returned suggestion is a recorded failure; do not reconstruct hidden text. A valid synthetic answer that violates a domain rule is an assessed error rather than damaged input.

Keep `model_output` and `final_suggestion` stages explicit. Only a final suggestion requires the existing exact disclaimer suffix. Do not append it during replay or hide preceding content when matching it. The English doctor rule does not become a rule of the Russian coffee catalogue. This stage introduces no new requirement to upsell on every question or always follow `goes_with`.

## 3. Corpus and independent measurement

The planned 60 cases contain 30 per language. Five families each contain 12 cases, six per language: price/currency; form/quantity/units; product relations/contradictions; unsupported facts; completeness/manager hint. Within each family/language, two close correct/incorrect pairs serve development and one distinct pair serves verification: 40 development and 20 holdout overall. Holdout readiness requires 10 correct and 10 incorrect cases, ten per language.

Categories are report metadata and may overlap. Verify subtype coverage before approving the corpus. Technical malformed-input/network/exception tests are additional tests, not part of the sixty content cases. If group independence prevents the proposed balance, preparation remains incomplete; do not silently change the counts or split relatives.

A group includes common original answers, mutations, close paraphrases, translations of one template and variations of one claim. It stays entirely in one partition. Examples already disclosed in the specification/rules, exploratory checks or T11 belong to development or extra regression, never blind verification.

A separate corpus custodian prepares the holdout without implementing/tuning the evaluator. Humans confirm reference labels. The implementation author and code reviewer receive development cases only; holdout cases/labels/access records stay in custodian-controlled storage and out of their checkouts, prompts, logs and artifacts until the candidate is frozen. Isolation is enforced by supplied context, not by a folder called `holdout`.

Before the first independent run pin source, fact, question, corpus, rules, labels and evaluator-code revisions, groups and access state. Run the unchanged twenty once for acceptance. A failed threshold remains a failure, with all cases and original reports retained. If its results inform tuning, subsequent runs on those twenty are regression; a new independent acceptance set requires a separate decision. Publication of holdout examples also ends their blind status for future development. No statistical guarantee about arbitrary traffic follows from this engineering set.

## 4. Reports, metrics and CLI

Reports use `report_kind=quality-evaluation` and `schema_version=1`. Preserve the old `EvaluationReport.passed` binary meaning. JSON and Markdown come from one result model, with stable case order, source/rules/evaluator versions, complete question/answer, human status, claim and evidence spans, expected source values, reasons and unchecked fragments. Summaries link to individual cases. Run timestamps and local locations do not enter the reproducible content comparison.

For each language/category and overall, show total cases, evaluated cases, the three verdict counts, failures, pending/disputed/unresolved references, false confirmations and false rejections with absolute denominators. Let E contain `evaluated` cases; C contain cases in E with `confirmed/correct` human labels; W contain cases in E with `confirmed/incorrect` labels. Other labels and execution failures do not enter C/W and are counted separately.

False-confirmation rate is `count(W with factual_verdict=confirmed)/len(W)`. False-rejection rate is `count(C with factual_verdict=error)/len(C)`. Manual review can belong to C/W but enters neither error numerator. A zero denominator is null. Also show `manual_review/len(E)` and `len(E)/total`. Example: two human-correct references, one `evaluated/error`, one `evaluator_error/null`, give false rejections 1/1, two references and one failure, not 1/2. The acceptance manual-review bound always uses all twenty.

The CLI has two explicit modes:

| Mode | Exit 0 | Exit 1 | Exit 2 |
|---|---|---|---|
| `replay` | All recorded answers confirmed | At least one error or manual review | Incomplete run or execution/input failure |
| `acceptance` | Ready independent set meets evaluator thresholds | A numerical threshold fails | Acceptance cannot be established |

Always show both `answer_set_status` and `evaluator_gate`. In acceptance, synthetic answer errors can be expected material: an evaluator pass does not turn those answers into correct ones. Readiness requires exactly twenty fixed independent cases, all evaluated and all human-confirmed definite correct/incorrect, the 10/10 truth and language balances, and no contamination. Unresolved labels, failures, wrong composition or empty input produce `not_ready`/2 rather than a reduced successful subset. Empty replay also returns 2.

Write both reports outside the event loop into a new caller-selected run directory, publishing the pair only after both are prepared successfully. Reject existing destinations, input-file collisions and aliases before writing. Do not overwrite source records or historical T11 artifacts. A failed second write cannot leave the first file advertised as a successful final report. Sanitise failure output; malformed records do not become traceback dumps or success counts of zero.

## 5. Modules

| Path | Responsibility |
|---|---|
| `src/reply_assistant/quality_schema.py` | Closed input, projection, claim and report models |
| `src/reply_assistant/quality_corpus.py` | Async decoding, source/package verification and label isolation |
| `src/reply_assistant/quality_facts.py` | Verified source-wide typed fact index |
| `src/reply_assistant/quality_rules.py` | Finite parsing, coverage, comparison, obligations and aggregation |
| `src/reply_assistant/quality_report.py` | Metrics and shared JSON/Markdown result |
| `scripts/evaluate_quality.py` | Explicit offline mode and exit behaviour |
| `tests/test_quality_*.py` | Distinguishing unit/integration tests |
| `tests/acceptance/test_quality_*.py` | Owner-authored acceptance contracts |
| `evals/quality/v1/` | Public schema, source annotations, format examples and forty development cases |

These paths exist in the repository; [tasks.md](tasks.md) links the submitted implementation and distinguishes it from acceptance. `knowledge_base.py`, `suggestion.py` and `checks.py` retain their existing behaviour. `evaluation.py` and `evaluate_live.py` remain the historical live evaluator. Owner instruction/specification/acceptance paths change through separate owner PRs; implementation issues cannot rewrite them.

## 6. Delivery stages

### Stage 1: contract and input data, E01-E05

E01 defines the complete finite rules; E02 defines structure, semantic invariants and source annotations. E03 prepares forty development and twenty separately held candidates, with obligations before answers and honest pending labels. E04 implements loading in two bounded issues: structural models/document decoding, then package source/hash/evidence/fact/reference/lineage/split checks and projection isolation. E04 can start after published E02 without waiting for E03 and is complete only after both issues.

The stage exit is E05: approved rules/format, genuinely human-confirmed development labels, pinned input revisions and technically accepted complete E04. Until then E06-E09 do not start. Contract/format approval does not certify human labels or let an implementation author invent grammar.

### Stage 2: deterministic fact assessment, E06-E09

Build typed facts, implement only the finite constructions and normalisation, account for both fields completely, then verify obligations/metadata and aggregate reasons. Test faithful paraphrases against close wrong values, mixed subjects, protected context, unknown tails, equal/conflicting prices and domain stems in negation. Forbidden metadata must never influence assessment.

### Stage 3: reports and offline CLI, E10-E13

Implement exact metrics/readiness, shared JSON/Markdown, real entry point/exit codes and safe off-loop report publication. Verify failure denominators, null rates, 0/0/4 and a fifth manual case, missing labels, write failures and collisions. Check existing API/generator/YAML/T11 compatibility on the integrated candidate; E13 is a verification gate, not a decorative tests-only PR.

### Stage 4: independent acceptance, E14-E16

Freeze code/rules/sources/annotations/corpus/labels/access state, evaluate the closed twenty once, check each result and denominator and retain original evidence. A completed measurement may produce pass, fail or not_ready. Publishing holdout data/reports is a separate release decision with inspection of actual outgoing content.

## 7. Verification and risks

| Requirements | Owner | Falsifying observation |
|---|---|---|
| Q1-Q5, A1-A2 | Corpus/models/loading | Wrong hash, duplicate/lost case, fake human label or split relatives |
| Q6-Q8, A3-A5, A8 | Typed facts and rules | Faithful paraphrase rejected, wrong typed value accepted or foreign subject selected |
| Q9-Q12, A6-A7, A10 | Coverage and compatibility | Uncertainty confirmed, failure called factual error, ignored hint or changed generator |
| Q13-Q15, A9 | Reports/metrics | Hidden denominator, contradictory reports or all-manual claimed as automation |
| Q16-Q17, A9 | Independent gate | Tuned-on holdout or synthetic mistakes called model error frequency |
| Q18, A11-A12 | CLI/delivery | Changed old `passed`, accidental client call or success without complete reports |

Each new test names a distinguishable defect and its predicted failing test names under mutation. Test metadata invariance, value changes, leftover-content coverage and real CLI process outcomes. Tests need no network/key and fake only I/O boundaries. Before each PR run all six commands from AGENTS.md and report actual output.

The grammar may fail to cover sixteen of twenty cases; preserve that failure instead of quietly widening rules or thresholds. Human labels/source annotations may be wrong and need grounded review. Full text coverage and procedural holdout isolation are explicit properties to verify. Semantic evaluation 002 does not silently amend the generator's verbatim rules or historical T11 checks.

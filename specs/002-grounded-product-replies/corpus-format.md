# Corpus format 002

**Status:** prepared format and agent-prepared source annotations. The format examples are not the planned 60-case corpus, human reference labels or a production loader.
**Contract:** [specification](spec.md), [plan](plan.md), [rules](rules.md), and the [structural schema](../../evals/quality/v1/schema.json).

## 1. Artifacts and ownership

| Artifact under `evals/quality/v1/` | Purpose |
|---|---|
| `schema.json` | Structural schema of four document kinds |
| `sources.json` | Two public catalogues and pinned rule bytes |
| `facts.json` | Nine product annotations and predicate support, `agent_prepared` |
| `examples/questions.json` | One question-obligation example |
| `examples/corpus-valid.json` | Structurally valid example with `partition=examples`, pending label |
| `examples/corpus-invalid-type.json` | Intentional boolean version |
| `examples/corpus-invalid-binding.json` | Intentional wrong fact-file hash |
| `examples/corpus-duplicate-key.json` | Intentional identical repeated JSON key |
| Future `development.json` | Forty development cases, pending preparation/human confirmation |

The schema owns exact fields, structural types, requiredness and enumerations. This document owns semantic invariants that one structural schema does not express. A disagreement blocks readiness; an implementer cannot select the more convenient interpretation. Holdout data stays in separate custodian-controlled storage before the independent measurement. Format examples never count toward sixty or acceptance.

## 2. Decoding

Input is UTF-8 JSON with exactly one root object. Empty files, bad encoding, extra content after the object, null/list/scalar roots and NaN/Infinity are invalid input. Reject every duplicate key at any depth, even identical values, before building a dictionary and before Pydantic validation.

Every field listed in the schema is required. Nullable means an explicit null is allowed, not that omission is allowed. Unknown fields are forbidden recursively. Require actual integer `schema_version=1`: the string '1', float `1.0` and boolean true are not interchangeable with it. The same lexical integer rule applies to span indices and other integer fields. Do not strip or normalise answer strings on loading; empty answer text remains assessable data.

Standard Python JSON decoding must precede strict Pydantic validation. JSON Schema's numeric integer semantics alone do not distinguish lexical `1` from `1.0` as this loader contract does. Direct `model_validate_json` without duplicate detection is not the contract path. Fact decimals are strings, never JSON floats. Structural model/decoding acceptance is separate from package semantics and factual assessment.

## 3. Versions, hashes and roots

All documents have `schema_version=1`. `document_kind` selects `quality_sources`, `quality_facts`, `quality_questions` or `quality_corpus`. SHA-256 values are 64 lowercase hexadecimal characters.

Hash original file bytes, not reserialised objects. Sources pins catalogue YAML and rules bytes; Facts and Questions each pin Sources bytes; Corpus pins Sources, Facts and Questions bytes. A changed input requires a newly agreed pinned set. A document does not embed its own hash.

`question_sha256` pins one Question: serialize its JSON object with `ensure_ascii=False`, `sort_keys=True`, `separators=(',', ':')`, `allow_nan=False`, then UTF-8 without a trailing newline. Preserve array order, Unicode and spaces inside string values. This is the project's specified serialization, not proof of preparation chronology or human authorship. E03 preparation records establish obligations before answers.

Resolve `Source.path` against an explicitly supplied project root, not process CWD or the JSON file's directory. Version 1 permits only `kb/example-en.yaml` and `kb/example-ru.yaml`. Reject absolute paths, traversal, URI values and any symlink component within that root before reading source content. No environment file, access record or neighbouring directory is needed.

## 4. Sources and Facts

Sources has `rules_id=factual-assessment-v1`, `rules_sha256` and its Source list. Source IDs are unique; a path cannot be registered twice under different IDs. Language must match the pinned YAML.

Facts pins Sources and contains `review_status`, `confirmation_ref` and ProductFacts. `agent_prepared` has null confirmation. `human_confirmed` requires actual human confirmation and a nonempty evidence reference; the field itself is not authentication or proof of who entered it.

| Object | Required semantic checks |
|---|---|
| ProductFacts | Unique source/product pair, existing product, declared F01-F08 profile, quantity role, facts and predicate support |
| Fact | Unique ID within profile; predicate, value type, value, unit and derivation consistent with its source |
| Evidence | Allowed string leaf, exact nonempty half-open span and quote |
| Support | One entry per predicate; supported requires a Fact; unresolved differs from absent |

Name, full form and description retain source strings. Price uses `value_type=decimal`, an N02-normalised numeric string with a dot and no thousands separators or removed trailing zeroes, plus USD/RUB. Quantities use `integer`, `[1-9][0-9]*` and the declared unit. Filter size is text, preserving `02`. `goes_with` is a reference to an existing product ID with null unit. Text components have null unit. A filter's kind comes from its name/description rather than the word 'упаковка'.

Derivations are closed: `literal` for an exact value; `decimal` for number/currency from price; `unit_alias` for digits/unit under N03; `profile_component` only for a component explicitly allowed by the F-profile, such as 'стальные' -> 'сталь'. No arbitrary description inference or new synonym. Price evidence covers both number and currency; quantity evidence covers both number and unit. Incompatible predicate/value_type/unit is `inconsistent_fact`, not a model error.

Quantity role describes the form's quantity. The spoon has `form_quantity=5 g` and `quantity_role=unresolved`, without inferred object/portion mass. A mass quantity stated for a package alone does not establish the mass of the object; object_mass remains unresolved until that relationship is established. This does not extend unresolved to item counts or volume quantities with other explicit source roles. The grinder's 'за раз' establishes batch capacity. Do not resolve these roles by product-ID branches or by copying a neighbouring product's interpretation.

Support describes the source, not the answer's human verdict. `absent` means checked absence in the complete pinned source under the supported predicate meaning; `unresolved` means ambiguity. Current sources have no delivery, stock or treatment-result facts. Reconsider those annotations on source changes; an absent top-level field is insufficient if the description carries the property. Unsupported annotation cannot establish an answer error.

Explicit Support has priority, but `supported` requires a Fact of that predicate. `absent`/`unresolved` together with a Fact of the same predicate is inconsistent. Without explicit Support, an existing Fact implies supported and a missing Fact implies unresolved, never absent. For `product_id=null` general delivery/stock/treatment questions, general absence requires all products of the source annotated and each explicitly absent with full-source grounds; otherwise it is unresolved. One product fact does not become company policy.

### Closed directed relations

`goes_with` is the complete directed set of each source product. The existing knowledge-base model treats an omitted optional list as empty. Every ProductFacts requires explicit `goes_with` Support: supported for a nonempty list, absent for an empty list. Facts must contain all and only source edges, once each, with evidence pointing to that array element. Missing/extra/duplicate edges or inconsistent Support fail before assessment.

R08 checks membership of the specific N1 -> N2 pair, not just whether some relation exists. An unlisted target is an unsupported relation error under both supported and absent states. Infer neither inverse nor transitive edges. This assesses listed source relations, not physical incompatibility. Powder -> Spoon is listed; Spoon -> Powder and Powder -> Travel Pill Box are not. The spoon's unresolved mass stays unresolved independently.

## 5. Evidence spans

Evidence pointer is a JSON Pointer into parsed YAML. Allowed string leaves are `/products/{index}/{id,name,form,price,description}`, `/products/{index}/goes_with/{index}`, `/reply_rules/{index}` and `/disclaimer`. Reject other pointers. A Fact's evidence belongs to its product; referring to another product is not a way to borrow its property. Relations have their own explicit facts.

Offsets are Unicode code points of the decoded source string, not YAML bytes or UTF-16. Require `0 <= start < end <= len(string)` and `string[start:end] == quote`. Evidence for facts never points into a model answer or human verdict. A fact may reference several source fields; numeric and currency spans can share a price pointer with distinct offsets.

Reject missing, non-string, null or wrong-product targets rather than fixing them. Facts must cover all nine products of the current manifest. A new source/product without annotation is not assessed through a partial index.

## 6. Questions fixed before answers

Questions pins Sources and has a nonempty list of uniquely identified Question objects. Each specifies source, message (1-2000 characters and not whitespace-only), language, nullable place/topic, required claims/actions, allowed `kb_match` values and nonempty basis.

RequiredClaim names a field (`customer_reply`/`upsell_hint`), subject product ID or null, required nullable `target_product_id`, predicate and stance (`affirmed`/`unknown`). A `goes_with` obligation requires both a nonnull subject and a nonnull target existing in the selected source; it names that directed pair, not any outgoing edge or all outgoing edges. Every other predicate requires an explicit null target. Values come from source facts, never a prewritten expected answer. RequiredAction names its field and `handoff`/`doctor`. A manager-only fact does not answer a customer-field obligation. Doctor obligations follow the particular source/question; the English health rule does not apply automatically to Russian coffee.

For a question specifically asking whether Zeolite Powder pairs with Measuring Spoon, the obligation fixes subject `zeolite-powder-200` and target `measuring-spoon`. A claim about Capsules does not satisfy it even though Powder -> Capsules is a valid separate edge. A supported claim answering the requested Powder -> Spoon pair need not list every other edge. The target is fixed before the answer, included in the assessment projection and compared during E09. An absent or invalid relation target is `unknown_reference`/invalid input during package validation; first-unit decoding enforces its presence as a nullable structural field.

Place is fixed before the answer for R10/R11. Topic is delivery, stock, treatment_result or null. Mention in a question does not establish catalogue membership. A nonnull product ID must exist. Null can describe a general topic or unknown product; with a product-specific predicate such as name/price it remains unresolved and requires manual review even if all text was parsed. Version 1 does not infer unknown-product identity from question text or confirm such an obligation from absence.

Allowed `kb_match` values are a nonempty unique subset of found/partial/none, grounded by basis explaining source coverage. Do not copy the evaluated answer's metadata into that set. Annotated Questions are fixed-corpus contracts, not automatic understanding of arbitrary future requests.

## 7. Corpus and observations

Corpus pins three document hashes and has partition (`development`/`holdout`/`examples`) and a nonempty Case list. Examples validate format only and are ineligible for acceptance. Replay may assess another nonempty subset; filename alone does not prove full size/balance. Acceptance composition belongs to its gate and the custodian.

Case contains unique id, group_id, question_id/hash, nonempty unique categories from the plan's five families, Observation, separate question/answer Origins and Label. A group stays in one partition. Duplicate case IDs or crossing group IDs across supplied partitions invalidate their combined package. The implementation author validates the supplied portion; it does not receive closed twenty merely to perform that check.

| Observation outcome | Stage | Answer | Error code |
|---|---|---|---|
| `answer` | `model_output` or `final_suggestion` | Required four-field Answer | null |
| `provider_error` | null | null | timeout/connection/rate_limit/server/unknown |
| `suggestion_rejected` | null | null | shape/product_exists/no_forbidden_claim/unknown |

Answer has exactly customer_reply, upsell_hint, upsell_product_id and kb_match. Preserve strings, including empty ones. An unknown nonnull upsell ID is valid recorded data for later content assessment; rejecting it here would hide negative cases. Unknown `kb_match` outside its three values is structurally invalid.

A recorded final T11 Suggestion is adapted by explicitly selecting the four fields, setting final_suggestion and retaining its original record reference. Checks/usage are not evaluator truth. If a provider shape rejection was observed, record that rejection; do not reconstruct an absent text.

Execution status is produced by evaluation, never trusted as a corpus field. Valid recorded failures become recorded_failure/null; malformed input becomes invalid_input, evaluator failure becomes evaluator_error. A structurally valid incorrect answer stays assessable, with evaluated and a later factual verdict.

## 8. Provenance and human labels

Origin has kind, reference, sha256, parent_case_id, record_pointer and generation, with every nullable field present. Agent/human authored origins need no reference/hash, but either supplied value requires the other. Recorded origins require a real original artifact reference/hash and record pointer (empty pointer means root), with null parent. Derived origins require an existing parent in the same group/partition, without cycles. Question and answer origin are independent. Incoming artifact references do not authorize network fetching or publishing restricted content.

Generation keeps provider, model, max_output_tokens, temperature, input_tokens, output_tokens, attempts and run_reference. Fields are required but unknown values stay null. Temperature is the original string; output cap/attempts are positive integers and token counts nonnegative. Recorded answer origin requires the Generation object even if all parameters are unknown; question origin has null generation. Agent/human authored and derived origins have null generation/record_pointer. A changed derivative is not the original model output; parent parameters remain in lineage. Do not include keys, authorization headers or raw request dumps, or replace unknown with zero.

Label contains status, proposed_verdict, verdict, rationale, evidence, reviewed_by, reviewed_at and confirmation_ref. Proposed verdict can be an agent suggestion and never enters reference metrics. Pending has null actual verdict and all three confirmation fields null. Confirmed requires a verdict, nonempty rationale and all confirmation fields nonempty. Reviewed timestamp is RFC3339 UTC ending in Z. Disputed records have unresolved verdict, nonempty rationale and the same actual-review evidence fields. Human-confirmed unresolved records preserve uncertainty but cannot enter C/W or a ready holdout.

Label evidence uses source spans and remains label/report metadata; rationale is grounded in the source. Do not force uncertainty into incorrect to balance the sample. The schema cannot authenticate a string: confirmed is used only after an actual human decision verified by the lead. Accepting the rules by delegation is not human labelling of individual answers. The supplied example is pending/proposed-correct, with null reviewed_by; it creates no human reference.

## 9. Assessment projection

Loading retains a full Case for reporting but creates a separate allowlisted assessment input: verified source and ProductFacts, Question without id/basis, and Observation with stage/answer. Do not pass an entire Case or arbitrary full dictionary. Source annotation provenance does not decide a factual verdict once its input gate passes.

Exclude case/group IDs, partition, categories, all origins, labels/proposed verdicts/confirmation details and case filenames. The assessment function cannot recover them through globals/files. Metrics receives completed automatic results and labels separately. A test changes all excluded metadata with identical permitted content and requires an identical automatic result.

## 10. Input errors and precedence

| Code | Stage/example |
|---|---|
| `read_error` | Missing/unreadable file or other file OSError |
| `encoding`, `json_syntax`, `duplicate_key`, `nonfinite_number` | Before model validation |
| `schema`, `unsupported_version` | Structural/type failure; unsupported actual integer version |
| `duplicate_id`, `unknown_reference`, `lineage_cycle` | Identity and reference failures |
| `source_path` | Forbidden or symlink source resolution before reading source content |
| `source_hash`, `binding_hash`, `question_hash` | Pinned-byte or obligation binding mismatch |
| `invalid_evidence`, `inconsistent_fact` | Invalid source span, foreign owner or contradictory typed fact/support |
| `invalid_observation`, `invalid_label` | Cross-field invariants |
| `split_leakage`, `invalid_composition` | Cross-partition or acceptance readiness failure |

Order is decoding, structure, uniqueness/references, hashes, Evidence/facts, cross-field invariants, then mode-specific conditions. Source-path safety precedes source reads. Version type failure is schema; an integer other than one is unsupported_version. File-read errors necessarily precede decoding the unread file.

Package loading is atomic: an invalid document/case stops assessment of the whole package before its first evaluation and produces invalid_input/exit 2. Unknown case counts are null, never successful zero. Valid recorded provider/service failures remain cases with recorded_failure rather than corrupting the package. An invalid case cannot reduce the acceptance denominator: readiness is not_ready/2. Safe output uses codes and known record/field identifiers, not raw input, arbitrary exception text or full ValidationError dumps.

E04 has two implementation units: document decoding/schema first; full package invariants and projection second. The first unit is not a claim of package validity. E05 separately requires approved rules/format, technically accepted complete E04 and genuine human-confirmed development labels before E06-E09.

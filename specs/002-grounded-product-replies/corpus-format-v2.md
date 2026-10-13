# Extended question and report contracts

This extension adds explicit question obligations and complete offline reports. [Version 1](corpus-format.md), the original catalogues, public development bytes, finite [claim grammar](rules.md), generation and historical reports retain their existing meanings. The extension does not confirm a reference label or authorize a model call.

## Question document

`document_kind=quality_questions_v2` and actual integer `schema_version=2` select the extended document. Its Sources binding and question list use the existing contract. The legacy `quality_questions` discriminator remains strictly version 1; changing its version to 2 does not upgrade a document. Sources, Facts and Corpus retain their version 1 wire format and bind the exact new question bytes through SHA-256. The [version 2 schema](../../evals/quality/v2/schema.json) describes the extended question document.

Every extended Question keeps all original fields and requires two additional arrays. Empty arrays are explicit; omitted or unknown fields are invalid. The canonical question hash includes both arrays in their original order. IDs and basis stay out of the assessment projection; the new obligations are allowed assessment inputs, without labels, origins, categories or partition metadata.

| Field | Record | Semantics |
|---|---|---|
| `required_recommendations` | `field=upsell_hint`, nonempty `product_id` | Require a recognized manager recommendation of this particular source product. At most one record is allowed because the answer carries one upsell product ID |
| `required_unknown_information` | `field=customer_reply/upsell_hint`, required nullable `product_id`, nonblank `property` string | Record the request to acknowledge uncertainty about this particular additional property. A descriptor is not a new factual predicate or evidence that the source lacks the property |

Every nonnull product belongs to the selected source, including an unknown-information subject. A null subject describes a general request. Duplicate unknown-information tuples `(field, product_id, property)` are invalid; descriptors preserve exact text and are not translated, normalised or interpreted as keywords. The existing source and question provenance still establishes why the obligations were chosen before answers.

## Assessment limits

A recognized R13 directive must name the requested recommendation target, separately from the answer's own `upsell_product_id`. Matching a different existing product and its ID is insufficient. A mere factual mention or price does not establish a recommendation. A fully parsed missing directive is incompleteness; a recognized different target is a recommendation mismatch. Protected context or an unsupported possible recommendation remains manual review. Existing metadata and domain violations keep their precedence.

Arbitrary property descriptors have no new automatic fact or absence grammar. Each unknown-information obligation therefore adds an explicit unresolved reason with its field, property and subject. A correct price, greeting or handoff does not confirm this obligation. Do not declare the answer wrong merely because the construction is unsupported. A separately proven error still gives error with the uncertainty retained. Automatic resolution of such descriptors requires a future versioned grammar, source annotations and distinguishing examples; this extension supplies no product-specific shortcuts or judge model.

The semantic grammar remains `factual-assessment-v1`; version 2 identifies the additional question contract. Supported claim parsing and normalisation are unchanged. The report preserves the question contract version and exact document hashes so this extension is distinguishable from the earlier inputs.

## Complete report schema

The real offline CLI emits `report_kind=quality-evaluation/schema_version=2` for both legacy and extended inputs. Metrics, acceptance readiness, replay/acceptance exit codes and the historical live evaluator's binary `passed` stay unchanged. Existing report API callers default to schema 1 and retain its original payload; schema 2 is explicitly selected by the CLI or by `build_report(..., schema_version=2)`.

Each version 2 case keeps the original summary fields and adds:

- `context`: full question, question contract version, group/question IDs and question hash, complete Observation, question/answer Origins and complete Label. Observation retains all four Answer fields, exact strings including empty strings, stage, and recorded error code. A recorded failure retains a null answer; an evaluator failure retains the received observation without inventing a factual verdict.
- `claims[].field`: customer_reply or upsell_hint. Claim offsets refer to that original field, never to concatenated texts.
- `coverage`: per-field protected status/reason and original unchecked spans with exact slices. When no field assessment exists, coverage is null rather than an empty successful check.
- `document_sha256`: original byte hashes of Sources, Facts, Questions and each Corpus, in addition to existing catalogue/rules hashes.

JSON and Markdown derive these details from the same report records. Markdown includes the manager hint, recommendation ID, knowledge-base match, stage/failure, obligations, origins, reference and field-attributed claims and coverage. Report schema 2 rejects entries without full context or claim field attribution. No new metadata is passed into factual assessment.

Complete reports carry supplied answer text, provenance and label notes. Inspect actual outgoing content before sharing; report generation alone authorizes no publication. Historical report files and the original pending preparation bytes are never rewritten by this extension.

The [public example](../../evals/quality/v2/example/corpus.json) is a format and replay fixture with pending labels, not independent acceptance material. Previously measured closed cases, if used after changes, are regression evidence only.

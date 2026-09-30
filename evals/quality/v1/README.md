# Quality evaluation inputs

These artifacts define the first offline quality-evaluation format. They contain two fictional public sources, agent-prepared annotations for nine products and one pending format example. They are not the planned sixty-case dataset, human reference labels or a working evaluator.

Read the [specification](../../../specs/002-grounded-product-replies/spec.md), [plan](../../../specs/002-grounded-product-replies/plan.md), [rules](../../../specs/002-grounded-product-replies/rules.md) and [semantic format](../../../specs/002-grounded-product-replies/corpus-format.md). `schema.json` owns structural types; the format owns decoding and package invariants. Source YAML remains in `kb/example-en.yaml` and `kb/example-ru.yaml`.

| File | Role |
|---|---|
| `schema.json` | Closed structures of Sources, Facts, Questions and Corpus |
| `sources.json` | Catalogue and rule byte hashes |
| `facts.json` | Source annotations, exact evidence and support states |
| `examples/questions.json` | Question obligations fixed independently of an answer |
| `examples/corpus-valid.json` | Structurally valid pending example, partition examples |
| `examples/corpus-invalid-type.json` | Intentional schema error: boolean version |
| `examples/corpus-invalid-binding.json` | Intentional semantic error: wrong Facts hash |
| `examples/corpus-duplicate-key.json` | Intentional decoding error: identical repeated key |

The invalid-binding example can satisfy the structural schema and still be invalid as a package. The duplicate example must be read as raw JSON: decoding into a normal dictionary first destroys the defect. Unknown upsell IDs or empty answer text can be valid recorded data with content errors; the loader does not hide them by applying the factual verdict early.

Facts remain `agent_prepared` with no human confirmation reference. The valid example has `pending`, a proposed correct verdict and null actual verdict/reviewer confirmation. Hashes bind original bytes; editing Sources, Facts, Questions or rules requires consistent downstream bindings. Format examples are disclosed development material, never blind holdout.

E04 starts with strict document models/loading, then package verification and assessment-input isolation. Full package loading and the evaluator are planned implementations; no offline evaluator command is advertised as available here. Human-confirmed development data is a separate E05 gate before parsing/evaluation work, and independent twenty-case readiness is verified later.

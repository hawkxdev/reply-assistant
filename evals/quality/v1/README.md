# Quality evaluation inputs

These artifacts define the first offline quality-evaluation format. They contain two fictional public sources, agent-prepared annotations for nine products, one pending format example, and forty development cases whose labels record the repository owner's human confirmation; the twenty holdout cases are not published here. The implemented evaluator and offline command are tracked in [task status](../../../specs/002-grounded-product-replies/tasks.md).

Read the [specification](../../../specs/002-grounded-product-replies/spec.md), [plan](../../../specs/002-grounded-product-replies/plan.md), [rules](../../../specs/002-grounded-product-replies/rules.md) and [semantic format](../../../specs/002-grounded-product-replies/corpus-format.md). `schema.json` owns structural types; the format owns decoding and package invariants. Source YAML remains in `kb/example-en.yaml` and `kb/example-ru.yaml`.

| File | Role |
|---|---|
| `schema.json` | Closed structures of Sources, Facts, Questions and Corpus |
| `sources.json` | Catalogue and rule byte hashes |
| `facts.json` | Source annotations, exact evidence and support states |
| `questions.json` | Twenty development question obligations fixed before answers |
| `development.json` | Forty development cases confirmed as the human reference |
| `examples/questions.json` | Question obligations fixed independently of an answer |
| `examples/corpus-valid.json` | Structurally valid pending example, partition examples |
| `examples/corpus-invalid-type.json` | Intentional schema error: boolean version |
| `examples/corpus-invalid-binding.json` | Intentional semantic error: wrong Facts hash |
| `examples/corpus-duplicate-key.json` | Intentional decoding error: identical repeated key |

The invalid-binding example can satisfy the structural schema and still be invalid as a package. The duplicate example must be read as raw JSON: decoding into a normal dictionary first destroys the defect. Unknown upsell IDs or empty answer text can be valid recorded data with content errors; the loader does not hide them by applying the factual verdict early.

Facts remain `agent_prepared` with no human confirmation reference. The valid example has `pending`, a proposed correct verdict and null actual verdict/reviewer confirmation. Hashes bind original bytes; editing Sources, Facts, Questions or rules requires consistent downstream bindings. Format examples are disclosed development material, never blind holdout.

E04 provides strict document models/loading, package verification and assessment-input isolation. The evaluator keeps human labels outside factual assessment and uses them afterward for metrics. Human confirmation and independent holdout isolation remain procedural evidence requirements: the CLI assumes case independence and cannot authenticate a confirmation reference or reconstruct access history.

From the repository root, replay the published development corpus into a new directory outside this input directory:

```bash
uv run python scripts/evaluate_quality.py replay \
  --package evals/quality/v1/development.json --out quality-results
```

The command writes `report.json` and `report.md`. Content findings or manual review return 1; an incomplete run or invalid input returns 2. Synthetic incorrect answers are expected in this corpus, so exit 1 does not mean the command failed to execute. Development replay is not independent acceptance. Do not treat a repeated run on disclosed or tuned-on cases as a new blind measurement.

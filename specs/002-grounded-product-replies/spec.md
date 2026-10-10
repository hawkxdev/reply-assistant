# Specification 002: grounded product replies

**Status:** the public product contract of feature 002. Implementation and corpus state, together with the limits of historical acceptance evidence, belong to [tasks.md](tasks.md). This document by itself starts neither implementation nor any new paid run.
**Result of the stage:** a labelled set of examples and a reproducible report on distorted facts, invented statements and errors of the automatic evaluation itself.

## 1. Purpose and user

The owner and the developer of Reply Assistant must see which answers match the knowledge base, where the model makes mistakes and where the automatic check is insufficient. The manager keeps a naturally worded draft reply; the stage does not replace generation with templates and does not change the product interface.

Natural rephrasing is allowed while the product name, price, quantity, units and the meaning of a property stay unchanged. For example, 'порошок в банке 200 г' instead of 'порошок, банка 200 г' is not a factual error. The check must not count every stylistic difference as a distortion of data.

The goal of the stage is a truthful measurement of errors on the declared set, not a green model result at any cost. The result does not prove quality on the real requests of a company or on arbitrary text.

## 2. Agreed decisions

- Generation stays natural; the service, the prompt and the knowledge base format are not reworked for this evaluation.
- The corpus uses only the two public catalogues of the project: the English one and the Russian one.
- Unambiguously checkable requisites are assessed by code; the reference labelling is confirmed by a human.
- There are three automatic outcomes: confirmed, error, needs manual review. The share of manual review is shown separately.
- A separate judge model, mandatory templates and a YAML migration are postponed.
- The corpus contains 60 examples: 30 per language, Russian and English. 40 examples serve rule development, 20 serve independent verification; close variants of one example stay in one part.
- On the independent verification part zero false confirmations is the requirement: any answer with an error established by the human reference that receives an automatic 'confirmed' blocks acceptance. This is a requirement for this set, not a guarantee for arbitrary future answers.
- On the independent part manual review of at most 4 of 20 examples (20%) is allowed. All 20 have confirmed human labelling; execution failures are not counted as manual review and are not excluded to reach the threshold.
- On the independent verification part zero false rejections is the requirement: an automatic declaration of error for an answer that is correct by the human reference blocks acceptance. Routing to manual review is not a false rejection and is limited by the common bound of 4 of 20.
- The first stage runs without new paid calls of the product model: saved answers and prepared examples with human labelling are used. New live runs are outside its scope.

## 3. Scope

Included: rules of human labelling, labelled examples on public data, automatic evaluation within the declared limits, replay of recorded answers without a network, reports with reasons and summary metrics, and a check of the evaluator itself on correct and incorrect examples.

Excluded: fixing generation, changing the product model, a new internal answer plan, assembling replies from mandatory blocks, a new reply_templates section, YAML migration, revising upsell rules, RAG and a vector database, new agent frameworks, a queue, storing working dialogs, authorization, deployment, connectors and automatic sending. The real catalogue of a company is a separate stage.

The first stage includes no new paid calls of the product model. The corpus is built from saved answers and prepared examples; human labelling is confirmed separately. Offline checks of the evaluator and acceptance of the implementation run without a key and without a network. A new live collection belongs to a later, separately agreed stage.

## 4. Example set and human reference

Q1. Every case is bound to a specific public catalogue and its version or hash. The record carries a stable ID, language, question, the full answer under evaluation and the manager hint, expected products and facts, grounds in the catalogue and the provenance of the example. For a recorded live answer the link to the originating run and its known parameters is preserved. Missing parameters are not guessed.

Q2. The set distinguishes the provenance of the question, of the answer and of the labelling. An agent may prepare a candidate, but its assessment is never presented as human. An example becomes a reference only after confirmation by a human; unconfirmed and disputed records are shown separately and do not raise the quality metrics of the evaluator.

Q3. The reference fixes the correctness of content and a reason: a correct answer, a specific error, or an unresolved doubt. An unresolved human reference is not used as unambiguous truth when false confirmations or false rejections are computed. The status of the automatic evaluation is stored separately from the human verdict and never rewrites it.

Q4. The corpus includes correct original formulations, permitted rephrases, wrong prices, currencies, quantities and units, mixing requisites of different products, invented properties, claims about unknown delivery or stock, questions without an answer and incomplete answers. For every material distortion a close correct example is selected, so that the check distinguishes the cause of the error instead of rejecting the whole class of texts. Both languages are represented.

Q5. Permitted variants and limits of the automatic check are fixed before its run in the corpus rules. After a failed answer one must not add only its text to an allowed list to reach a green result. A new permitted form requires an explainable general rule and a check on a close incorrect variant. Changes of labelling and of rules are versioned together with their reasons.

## 5. Automatic evaluation

Q6. The evaluator works with a recorded answer and a pinned source. It calls no model, does not fix the answer, does not repeat generation and does not change the original catalogue. Repeated evaluation of the same inputs with the same rule version yields the same verdicts and reasons.

Q7. Only explicitly supported kinds of facts and formulations are checked. An unfamiliar construction is not declared wrong automatically. Normalization of formatting is allowed when it preserves the value: the decimal separator, spaces and unambiguous currency and unit notation within the approved rules. One must not silently change the product, currency, quantity, rounding, unit or the meaning of a form. The concrete set of supported transformations is fixed before implementation in the technical contract.

Q8. The presence of the right number or name somewhere in the text is not enough. The check must account for the binding to the specific product and statement. Examples with negation, two contradicting prices, a foreign price next to the correct one and an additional unconfirmed property must not be confirmed by one matched fragment. If a rule cannot establish such a binding, the result goes to a human.

Q9. The outcome of an evaluated answer has one of three values:

| Outcome | Condition | What is visible in the report |
|---|---|---|
| Confirmed | All mandatory checks of the case pass within the supported limits, the facts match the source and no flagged unchecked content remains | Which facts and grounds were checked |
| Error | A specific violation of a case requirement or a contradiction of the source is established | Category, answer fragment, expected value or the ground of missing information |
| Needs manual review | An automatic rule cannot confidently resolve the content | What exactly remained unchecked and why |

When a proven error and a remaining doubt coexist, the overall outcome is 'error' and the doubt is preserved in the details. Without a proven error, any unresolved mandatory condition excludes the outcome 'confirmed'. A partial check of a price does not confirm the whole answer. Completeness of claim detection is itself a subject of the evaluator check, not an assumption made without proof.

Q10. The evaluation covers the customer reply and the manager hint. A correct upsell ID does not prove the correctness of the accompanying text. Factual distortions, unconfirmed statements, the absence of a mandatory answer to the question and violations of the acting domain rules are distinguished. The rules of generation and of allowed upsell are not changed at this stage.

Q11. A provider failure, a rejection of the answer by the existing service, a damaged corpus record and an error of the evaluator itself are not masked as a factual error of the received answer. They have a separate execution status and reason. For a missing or unevaluated answer no factual verdict is invented; such cases do not enter the denominator of successfully evaluated answers and are shown by a separate counter.

Q12. The acting checks of structure, product and forbidden claims remain. The permission to rephrase gives no exception for a domain prohibition. The evaluator does not weaken the filters of the service to accept an example and does not send the evaluated text to the customer.

## 6. Report and measuring the evaluator itself

Q13. The machine readable and the human readable reports agree on cases and outcomes. For every case the report shows the source, the question, the evaluated answer, the human labelling and its status, the automatic verdict, the reasons, the checked and the unchecked conditions. The unknown is not turned into an empty successful check. Secrets, private instructions and real company data do not enter public reports.

Q14. The summary shows absolute counts and denominators, not a single success percentage: the three automatic outcomes, execution failures, unapproved and disputed references, the split by languages and error classes. It stays possible to go from the summary to the concrete cases.

Q15. On confirmed human references the false confirmations of an incorrect answer, the false rejections of a correct answer and the share of routing to manual review are counted separately. The automatic accuracy metrics come with coverage: sending all answers to a human does not count as completed automatic evaluation. One must not show only accuracy on an easy subset while hiding the size of the other groups. For acceptance all 20 independent examples have confirmed human labelling. Manual review is allowed for at most 4 of 20 (20%); execution failures are counted separately, do not count as manual review and do not shrink the set to reach the threshold.

Acceptance conditions of Q15: zero false confirmations and zero false rejections on the independent verification part. An automatic verdict 'error' for an answer that is correct by the human reference is a false rejection and blocks acceptance; manual review is not a false rejection. Any false confirmation blocks acceptance, including a confirmation of a wrong price, quantity or invented property. Manual review is not a false confirmation; its bound is 4 of 20 independent examples. The condition does not prove the absence of errors outside the verification set.

Q16. The evaluation is not limited to the examples the rules were written against. The corpus contains 60 examples: 30 per language, Russian and English, 40 for rule development and 20 for independent verification. Membership in the parts is fixed before tuning; close variants of one example stay in one part. After an example has been used for tuning it no longer proves independent verification of the same version. This is an initial engineering set; statistical significance and quality on arbitrary answers are not proven by it.

Q17. Model accuracy and evaluator accuracy are shown separately. Human labelled artificial errors test the evaluator, not the error rate of the product model. Recorded live answers describe one concrete run, not all future answers. A correct rejection by the evaluator of an incorrect answer is a success of the check, not a success of generation.

Q18. The report and the run clearly distinguish a completed evaluation from fully confirmed answers. The outcomes 'error' and 'needs manual review' do not turn into a common green verdict. Machine statuses and exit codes are defined in the technical plan before the acceptance tests, with a separate execution failure outcome. The binary field of the previous report of task T11 must not silently get a new three valued meaning.

## 7. Examples of reference content

The table below illustrates the agreed behaviour. These fragments are contract examples, not a substitute for labelled full corpus records or independent acceptance evidence.

| Pair | Answer fragment | Content assessment and ground |
|---|---|---|
| Permitted form EN | Zeolite Powder comes as a powder in a 200 g jar and costs 18.00 USD. | The facts match the record zeolite-powder-200; the preposition is not a distortion |
| Wrong price EN | Zeolite Powder comes as a powder in a 200 g jar and costs 20.00 USD. | Price error: the catalogue says 18.00 USD |
| Permitted form RU | Бразилия Сантос: зерно в пачке 250 г, цена 690 RUB. | Name, form, quantity and price match the record |
| Wrong quantity RU | Бразилия Сантос: зерно в пачке 500 г, цена 690 RUB. | Quantity error: the catalogue says 250 г |
| Unknown delivery | We deliver to Atlantis within two days. | No supporting information exists in the public catalogue |
| Honest absence of information | I do not have information about delivery to Atlantis or delivery times. I can pass the question to a manager. | Matches the absence of information and the handoff rule |
| Complex fact binding | The answer names two products and several numbers, the rule cannot bind the prices unambiguously | Automatically needs manual review; the human verdict is determined by reading the specific full answer |
| Hidden contradiction | The answer contains at the same time the correct price and another statement about the price of the same product | One match with the catalogue gives no confirmation; a proven contradiction is an error, an unsupported construction requires manual review |

The full answer in the context of the question enters the corpus, not only this fragment. The manager hint, the disclaimer and the acting domain restrictions are checked as well. If an automatic rule does not yet cover a correct rephrasing, it flags manual review instead of declaring a correct answer wrong.

## 8. Acceptance of the stage

| ID | Requirement | Evidence |
|---|---|---|
| A1 | The source and version of every example are defined, the labelling has provenance | Check of the records Q1 to Q3, absence of agent labelling silently presented as human |
| A2 | Both public catalogues and pairs of correct and incorrect content are represented | Registry of classes Q4 and Q5; 60 examples, 30 per language, the 40/20 split of Q16 |
| A3 | Supported correct rephrases are accepted | Positive examples EN and RU, including the form used in task T11 |
| A4 | Substituted price, quantity, currency, product or an attributed checkable property are detected | Close negative examples in the supported area; the unknown is not confirmed |
| A5 | A correct fragment does not hide a contradiction or unchecked content | Examples of Q8 and Q9 with negation, several products, an extra statement |
| A6 | All three outcomes have distinguishable conditions and reasons | Checks of the outcome, of the priority of a proven error and of preserving doubts |
| A7 | Execution failures are separated from answer quality | Q11: provider, service rejection, damaged corpus and evaluation error do not distort the counters |
| A8 | Repeated offline evaluation is reproducible and calls no model | The same inputs and versions give the same content result, the model client is not called |
| A9 | The report does not inflate quality through manual review | Q14 to Q17: exact denominators, zero false confirmations and rejections on the independent part, manual review at most 4 of 20 |
| A10 | Generation and the working API are not changed for the evaluation | The previous contract checks of the service remain; the new logic is isolated in the evaluation |
| A11 | The new report semantics do not replace the old ones | The report version and the consumer migration are explicit; the results of task T11 keep their original meaning |
| A12 | No new paid calls of the product model and no publication of private data | Saved answers and prepared examples, offline checks without network and key, public catalogues; live collection outside the first stage |

Every new test names a distinguishable defect that it detects; assertions are not weakened to reach a green result. The rules are tuned and checked on different examples. Before implementation starts, the concrete inputs, expected verdicts, supported transformations and open parameters are fixed. All quality commands of the project remain mandatory for a pull request.

## 9. Corpus contract and acceptance evidence

| Parameter | What must be determined | What must not be done silently |
|---|---|---|
| Corpus composition | Verify the agreed class coverage, 40/20 parts and 30/30 language balance for the candidate | Split close variants of one example between parts or present the set as statistical proof |

The set size, the split, the error thresholds, the manual review bound and the absence of new paid runs are agreed. The [technical plan](plan.md), [rules](rules.md) and [corpus format](corpus-format.md) own the concrete contract; [tasks.md](tasks.md) owns implementation and evidence state. Examples prepared by an agent do not count as human references without confirmation by the owner. A stored report with `evaluator_gate=pass` does not by itself establish the tested code revision, authentic human confirmation or historical holdout isolation.

The structural corpus loader, task E04 of [tasks.md](tasks.md), depends only on the published format contract of [corpus-format.md](corpus-format.md) and its format examples, and may start before the corpus preparation of E03 is complete. The parser and verdict work, tasks E06 to E09, starts only after the gate of E05: human confirmed development labels and an accepted E04.

## 10. Compatibility and the next result

The YAML format, the API /api/suggest, the internal answer of the generator, the prompt, the retries, the fallback provider and the current domain checks are not changed by this stage. Free text is preserved. The proposals of the earlier draft about fully template output, a mandatory reply_templates section and changes to upsell rules are withdrawn from the current scope.

002 defines a new rule for evaluating natural form. The previous result of task T11 remains a correct result of the previous literal contract; the historical run and its artifacts are not rewritten. If the same saved answer is assessed by the new rules, that is a separate report with the rule version and a link to the original answer. With this publication the public requirements and acceptance rules are stated accordingly, without silently changing past checks.

The contract consists of the agreed technical plan, corpus and report format, assessment rules and published development inputs. Implementation and acceptance evidence are tracked in [tasks.md](tasks.md). The current local process applies; neither this contract nor an older delivery record authorizes new paid calls, cloud execution or release.

## Grounds

- [Specification 001: reply and upsell hint](../001-reply-and-upsell/spec.md).
- [Technical plan 002](plan.md).
- [Assessment rules 002](rules.md).
- [Corpus format 002](corpus-format.md).

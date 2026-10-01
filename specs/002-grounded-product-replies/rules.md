# Assessment rules 002

**Status:** accepted as the E01 rules contract of feature 002. It is not a program implementation and not confirmed human labelling of the corpus.
**Basis:** [specification](spec.md), Q5 to Q12; [plan](plan.md), sections 3.2 to 3.5 and the output gate of stage 1.

## 1. Purpose and scope

The rules define the supported evaluation constructions for the two public catalogues. They do not restrict the generator to templates and do not change task T11. An unknown construction is routed to a human; it must not be declared false only because it is absent from this table. The policy is named factual-assessment-v1 and evaluates the preservation of facts, separately from the old literal check of form.

All examples of this document are disclosed to the developer. They are used only for development and regression checks and do not enter the independent part. The number of examples in the tables does not set the corpus size: the agreed corpus separately contains 60 records.

The automatic function receives the text of both fields, the answer metadata, the annotated commitments of the question and the verified source. case_id, group_id, the set part, the error category, the human verdict and the mutation provenance are not part of its input. The presence of string examples in this document does not permit implementing a dictionary of ready answers.

## 2. Sources and notation

Sources: kb/example-en.yaml and kb/example-ru.yaml. Execution requires the SHA-256 of the original bytes and confirmed fact annotations with exact ranges of the string fields. Hashes and ranges are verified before evaluation. A mismatch means invalid_input, not an answer error. Private catalogues are not included in the public corpus.

| Notation | Meaning |
|---|---|
| N | The exact name of one product from the chosen source; it is not corrected by fuzzy search |
| A | A non negative decimal number by N02, without a sign and without exponent |
| C | An explicit code USD or RUB; another currency notation is out of support |
| Q | A positive integer count without grouping and without a fractional part |
| U | A unit from N03 |
| F | A form from the profile F01 to F08; values are extracted by grammar, not taken from a reference answer |
| D | The full description text of a specific N, including its meaning parts |
| PLACE | An exact destination fragment from the question annotation; it is not derived from the answer |
| TOPIC | A topic from the question annotation: delivery / stock / treatment_result |
| TYPE | The predicate of a fact: price, form, package_quantity, portion_mass, form_quantity, batch_capacity, section_count, filter_size, material, description, goes_with, delivery, stock, object_mass, treatment_result |

TYPE belongs to the statement, not to the number. 30 г за раз of the grinder is not the mass of the device. Filter size 02 does not equal the count 2. The source field, the question annotation and the human verdict have different owners.

The examples marked 'fact confirmed' below refer to a local statement. An overall confirmed is possible only after checking the whole text, the metadata and the commitments by A01 to A06.

## 3. Common normalization and bounds

| ID | Exact rule | Positive example | Close other example and outcome |
|---|---|---|---|
| N01 | Spaces between the fixed words of a construction may repeat; a newline by itself does not end a statement and equals an interword space only outside a number. The name N keeps the case and all letters of the source. The case of fixed service words is irrelevant | Zeolite Powder costs 18.00 USD | zeolite powder costs 18.00 USD: name not recognized, manual_review |
| N02 | Number: digits without grouping, or a first group of 1 to 3 digits and further groups of exactly 3, separated by one kind of space; the fractional part is optional, one separator dot or comma with at least one digit. A regular, a non breaking and a narrow non breaking space are allowed as thousands separator kinds. Decimal is built from the normalized string | 3 900 RUB; 18,00 USD | 3 9 00 RUB, 1,000.00 USD, -18 USD, NaN: manual_review; 18.01 USD in a recognized price of the powder: error |
| N03 | g/г mean grams, ml/мл millilitres, pieces/штук a count of items, sections/отделений a count of sections. A unit is compared together with its type; there are no conversions | 200 g and 200 г in a supported form | 200 ml instead of 200 g: error with a recognized form; 0.2 kg: manual_review |
| N04 | A size code is compared as a string, without removing leading zeros | size 02 / размера 02 | размер 2 with a recognized filter_size: error |
| N05 | A period and an exclamation mark end a statement, a semicolon separates full statements only after N07. A period inside A does not split sentences. A newline is not a boundary by itself | Two independent sentences about a price | A break after 'and', an unparsed comma with a new phrase: remainder, manual_review |
| N06 | No spelling correction, transliteration, homoglyphs, arbitrary morphology, rounding or currency substitution. Unicode NFC/NFKC is not applied to names automatically | The exact name from the source | A similar name with a Latin letter inside Cyrillic: manual_review |
| N07 | The context pass runs over the whole original field before splitting. The exact order, markers and scope are defined below; a protected field yields no positive statements even on an exact substring match | N costs A C as a separate statement | 'Does N cost A C?', 'N does not cost A C', 'If N costs A C': manual_review |

Punctuation cannot remove meaning. Quotes around a whole statement are not decorative formatting. A literal fragment D may contain punctuation from the source: first the whole construction with D is considered, then its boundaries; it is not cut at an arbitrary comma. Markdown markup, lists and parenthetical remarks outside the listed constructions remain an unchecked remainder.

### The finite context pass N07

1. First the unchanged forbidden claim stem checks run over both original fields. Context does not cancel their rejection.
2. A quote marker in a field protects the whole field, not only the text up to the first period. Markers: the double straight quote U+0022, single U+0027, backtick U+0060, « and », “ and ”, ‘ and ’, „ and ‚. U+0027 or U+2019 between two letters counts as part of a word, not as a quote. The presence of at least one of the other listed markers, including a single, unclosed or multiline one, gives protected_context for the whole field. Pairing and nesting are not guessed.
3. In a field without a quote marker the full R11/R12 and the exact policy R15 are recognized; only their own ranges are excluded from the negative marker search. A full R11/R12 is bounded by the start or end of the field or by the N05 terminators; a newline does not close it. The exact suffix R15 has its own boundary set by the source and does not mask the preceding text.
4. In the remaining ranges any question mark, or a separate lexical marker from the finite list, protects the whole field: if, unless, when, provided, suppose, hypothetical, not, no, never, cannot, can't, don't, doesn't, isn't, than, versus, instead, cheaper, more, less, or; если, когда, при, бы, допустим, предположим, не, нет, никогда, нельзя, чем, вместо, дороже, дешевле, больше, меньше, или. Comparison ignores case; a marker is bounded by a string boundary or a non letter, an internal apostrophe belongs to the word. The search runs before line folding and does not use case_id. These are conservative markers, not a universal language analysis.
5. protected_context excludes automatic fact extraction from the whole field and gives manual review for its content. An error of the previous domain filter, of the metadata, or a proven error of another unprotected field keeps the priority of A02. A protected field is not treated as empty in the completeness check.
6. Only the remaining unprotected field is split by N05. An unknown tail in the same fragment does not allow accepting its recognized prefix as a fact. An unsupported fragment is kept as a remainder; case and normalization rules are not extended by guess.

Distinguishing counterexamples: `Zeolite Powder costs 99 USD` plus a newline plus `if you order two jars.` gives manual review of the whole field; `Zeolite Powder costs 99 USD.` plus a newline plus `Hello!` give a proven price error. If the sentence with if stands after a period, the field is protected too: the first version deliberately does not resolve the range of the condition. A multiline or unclosed quote protects the whole field as well. This can raise the share of manual review; the 4/20 bound does not change because of it.

## 4. Product binding and constructions

The forms in the table define the whole fragment, not a substring search inside an arbitrary sentence. A recognized prefix with an unknown continuation of the same statement does not give an independent factual error: for example, a price with an unsupported discount condition as a whole requires manual_review. A statement becomes checkable only after its full boundary and a supported context are parsed; complete separate statements keep their own grounds. Context N07 and boundaries are checked first. Placeholders cannot absorb a neighbouring statement. Several fitting parses with different subjects or types give manual_review, not the first random result.

| ID | Type and full construction | Binding and normalization | Positive example and outcome | Close other example and outcome | Ground |
|---|---|---|---|---|---|
| R01 | price: 'N costs A C'; 'The price of N is A C'; 'N стоит A C'; 'Цена N: A C'; 'N: цена A C' | An explicit N in the same fragment, N01 to N02 | Zeolite Powder costs 18,00 USD: fact confirmed | Zeolite Powder costs 20 USD: error; 18 RUB: error | products[N].price |
| R02 | form: 'N: F'; 'N comes as F'; 'N выпускается в форме F' | An explicit N, the form profile F01 to F08 | Бразилия Сантос: зерно в пачке 250 г: fact confirmed | The same construction with 500 г: error | products[N].form |
| R03 | Compound form+price: 'N comes as F and costs A C'; 'N: F, цена A C' | A single N binds both parts inside one full statement. Each slot is checked separately | Zeolite Powder comes as a powder in a 200 g jar and costs 18.00 USD: both facts confirmed | The same fragment with 99 USD: error; an added 'and ships tomorrow' is not absorbed | form and price of the same N |
| R04 | description: 'N: D'; 'Description of N: D'; 'Описание N: D' | D matches the whole description of the chosen N. Comparison ignores only the case of the first letter of D after the introductory part; words and the remaining characters are preserved | `Описание Бразилия Сантос: Кофе средней обжарки с нотами ореха и шоколада.`: fact confirmed | The description of another product instead of D is not recognized: manual_review, or error when a statement about a foreign property is separately recognized | products[N].description |
| R05 | batch_capacity: 'N перемалывает Q U за раз'; 'N grinds Q U per batch' | Only Q and a mass U, an explicit subject | Ручная кофемолка перемалывает 30 г за раз: fact confirmed | 60 г за раз: error | The batch_capacity type from form |
| R06 | object_mass: 'N весит A U'; 'N weighs A U' | Only a mass U. With an unknown role of the source quantity component manual_review applies; the absence of mass must be proven by a complete unambiguous profile | У кофемолки 30 г за раз имеет явную роль batch_capacity; у ложки роль 5 g не определена | Ручная кофемолка весит 30 г: error; Measuring Spoon weighs 5 g: manual_review | The full source profile and its quantity_role, not a guess from a missing field |
| R07 | filter_size: 'N для воронки размера Q'; 'N for filter size Q' | The slot Q here is a digit code, not an integer after normalization | Бумажные фильтры для воронки размера 02: fact confirmed | размера 2: error | description, the filter_size code |
| R08 | goes_with: 'N1 pairs with N2'; 'N1 сочетается с N2' | Both names are explicit, the order of the relation is significant | Zeolite Powder pairs with Measuring Spoon: fact confirmed | The reverse relation does not follow automatically: error if it is absent from goes_with | products[N1].goes_with |
| R09 | stock: 'N is in stock'; 'N есть в наличии' | An explicit name does not turn presence in the catalogue into stock availability | There are no positive confirmed stock statements in the current sources | Zeolite Powder is in stock: error as an unsupported statement | Neither catalogue contains stock |
| R10 | delivery: 'We deliver to PLACE'; 'Delivery to PLACE takes Q days'; 'У нас есть доставка в PLACE'; 'Доставка в PLACE: Q дней' | PLACE is exact from the question, Q is an integer. Negative versions are not supported by this row | There are no positive confirmed delivery statements in the current sources | We deliver to Atlantis: error; 'We might deliver to Atlantis': manual_review | Neither catalogue contains delivery |
| R11 | Unknown delivery: 'I do not have information about delivery to PLACE or delivery times'; 'В базе нет информации о доставке в PLACE и сроках' | Only the full negative template, the N07 exception; the absence of this information in the chosen source is confirmed | The first construction with Atlantis: the fact of absent information is confirmed | The same text plus 'We deliver tomorrow': the added phrase stays unchecked, overall manual_review | Absence of delivery; reply_rules |
| R12 | Unknown stock: 'I do not have stock information for N'; 'В базе нет информации о наличии N' | The full N07 exception, the source contains no stock | В базе нет информации о наличии Бразилия Сантос: fact confirmed | 'N is not in stock': an unknown real absence, manual_review | Absence of stock; reply_rules |
| R13 | Manager directive: 'Offer N'; 'Consider N'; 'Предложите N' | Recognized as a manager action only in upsell_hint; it proves no fitness, binding or property. The named product must match a non null upsell_product_id | Offer Measuring Spoon with ID measuring-spoon: recognized hint | The spoon name with ID travel-pill-box: a mismatch error; a customer field with this directive: manual_review | Q10; the existing ID; the product contract of the two fields |
| R14 | Service phrases: 'Hello'; 'Здравствуйте'; 'I can pass the question to a manager'; 'Могу передать вопрос менеджеру'; 'Please ask a doctor about health questions' | The whole phrase matches. The last one is allowed only for the EN catalogue, where reply_rules prescribes a doctor. A greeting is allowed only in customer_reply, the other phrases in both fields | Hello! before a checked answer adds no fact | 'I already passed the question to a manager': manual_review, the action is not proven | reply_rules and the field separation |
| R15 | Disclaimer | The full kb.disclaimer string is recognized as a source policy. With final_suggestion the suffix must match '\n\n' plus the source string; model_output does not have to carry the suffix | The EN suffix from the source: checked | The mandatory final_suggestion suffix is missing: error; RU without disclaimer: no requirement | R11 of Specification 001; append_disclaimer |

The full R11/R12 and the disclaimer R15 are excluded from the negative marker search only in the order of N07 and outside a field protected by quotes; this does not permit extracting positive statements from other negations. The previous forbidden claim filter has its own independent priority and checks the original fields before semantic parsing, including negations and quotes. Its rejection is not cancelled by this table.

Pronouns it/он/она/это and carrying a subject between sentences are not supported. The compound R03 is the only permitted subject carryover between parts of one statement; between fields there is no carryover. Other combinations with and/и, 'respectively' enumerations, ranges and comparative prices give an unchecked remainder. A correct standalone statement does not allow ignoring the remainder.

Arbitrary properties, including detoxification, are not guessed from the presence of a keyword. Outside R01 to R15 a proven error is possible through the previous domain check; otherwise manual_review is required. This is an explicit boundary of the first version, not a statement that such text contains no errors.

## 5. Catalogue form profiles

The profiles use values from source.form and the confirmed source annotation. Branching on a specific product ID is forbidden in the implementation; an ID here only links a checkable example to its source. A wrong value in a supported profile is compared with the value of the chosen N and gives error; an unknown profile gives manual_review.

| ID | Profile and allowed F spellings | Separate facts | Source example |
|---|---|---|---|
| F01 | 'powder, Q U jar'; 'powder in a Q U jar'; 'a powder in a Q U jar' | form_kind=powder, container=jar, package_quantity=Q U | zeolite-powder-200: 200 g |
| F02 | 'capsules, Q pieces'; 'capsules, Q штук' | form_kind=capsules, package_quantity=Q count | zeolite-capsules-90: 90 pieces |
| F03 | 'paste, Q U tube'; 'paste in a Q U tube' | form_kind=paste, container=tube, package_quantity=Q U | clay-face-mask-100: 100 ml |
| F04 | 'steel spoon, Q U' | material=steel, form_kind=spoon, form_quantity=Q U, quantity_role=unresolved | measuring-spoon: 5 g kept as a form component; the mass of the object and of a portion are not derived from it |
| F05 | 'plastic box, Q sections'; 'plastic box, Q отделений' | material=plastic, form_kind=box, section_count=Q | travel-pill-box: 7 sections |
| F06 | 'зерно, пачка Q U'; 'зерно в пачке Q U' | form_kind=зерно, container=пачка, package_quantity=Q U | brazil-santos-250 and ethiopia-sidamo-250: 250 г |
| F07 | 'упаковка Q штук'; 'упаковка Q pieces' | form_kind=фильтры with a confirmed profile, package_quantity=Q count | paper-filters-100: 100 штук |
| F08 | 'стальные жернова, Q U за раз' | material=сталь, form_kind=жернова, batch_capacity=Q U | hand-grinder: 30 г за раз |

quantity_role=unresolved belongs to the source annotation, not to the human verdict of an answer. For F04 the literal form steel spoon, 5 g is checkable; replacing it with steel spoon, 10 g gives a form error. Statements about the mass of the spoon itself or of a portion under an unresolved role require manual review; the absence of a corresponding typed fact is not proof of an error. The role is not assigned by branching on an ID and is not silently resolved in E02. F07 takes the item type from name or description and the count from form: these are different ranges of the source.

Two products with the same form do not become one product. If a supported profile of another product is applied to N, the type and every component are compared; a component missing for N is not filled from a neighbour. A fragment matching any string of the base does not replace the parsing of the corresponding construction and the binding to the chosen product.

## 6. Question commitments and metadata

The question annotation is fixed before any evaluated answer exists and is confirmed by a human. It contains the chosen source_id, the language, the required subject IDs and TYPE, the expected kinds of answer when data is absent, and the allowed kb_match. Fact values come from the source, not from an expected answer string. Allowed kb_match values are explained by how the catalogue covers the question; they are not a disguised human verdict over the answer.

Each required relation fixes its directed subject and `target_product_id` before the answer. R08 checks source membership of the stated pair; M03/M04 check that the requested pair was answered in the required field. A different valid outgoing edge cannot satisfy the requested pair, and answering one requested pair does not require every outgoing edge. Non-relation commitments carry an explicit null target; the target is part of the question's permitted assessment input.

| ID | Condition | Resolution | Counterexample |
|---|---|---|---|
| M01 | upsell_product_id is not null and absent from the source | error by the existing product_exists | A known ID does not confirm the upsell_hint |
| M02 | kb_match is outside the justified set for the question | metadata error | found for a completely unknown delivery is not confirmed by a correct phrase about absent data |
| M03 | A required fact is absent and all text related to it is parsed | incompleteness error | Hello! with a mandatory price is fully recognized but does not answer the question: error; a bare name without a separate construction stays manual_review |
| M04 | A required fact is not found but a possible rephrase remains unparsed | manual_review | Semantic incompleteness must not be declared from one failed regular expression |
| M05 | A statement in upsell_hint refers to another existing product than upsell_product_id | Check the meaning by R01 to R15; a contradicting R13 directive gives error, a mere mention of another product is not an error by itself | Comparing two products or naming the main product is not forbidden by the name matching rule |

No new prohibition of upsell for health questions and no requirement to always pick a goes_with product are added. R08 checks only an explicitly made statement about a relation. The absence of a concrete upsell counts as an error only when it is already a justified requirement of the concrete question in the approved contract; the evaluator does not invent commercial policy.

## 7. Text accounting, statuses and aggregation

| ID | State | Outcome |
|---|---|---|
| A01 | A saved provider_error or suggestion_rejected without an answer, or a reading or structure error | recorded_failure or invalid_input; factual_verdict=null. The numerators of factual errors do not grow |
| A02 | A proven wrong fact, a metadata mismatch or a domain prohibition exists | factual_verdict=error; all unknown remainders are preserved as well |
| A03 | No proven error but an unchecked content fragment or an M04 commitment exists | factual_verdict=manual_review |
| A04 | All non empty fragments are recognized, facts and commitments match the source, no errors | factual_verdict=confirmed |
| A05 | A correct statement is repeated with the same normalized value | Not an error, both ranges are preserved; the verdict over the other fragments does not change |
| A06 | Two bound statements carry incompatible values, or one contradicts the source | error exactly for the wrong fact; the correct value is not a second error reason |

Every character of both fields belongs to a checked statement, a bounded service fragment, an allowed separator or an unchecked remainder. Ranges are given by Unicode code point offsets in the original string, end excluded. Normalization preserves the mapping of ranges to the original text. Overlapping parses with different meanings are not resolved by picking the first match. An empty string does not satisfy the commitments.

The classification matrix does not read the references; only a separate metrics module compares its result with confirmed/correct or confirmed/incorrect. For execution failures a separate status applies, as defined by the plan. When the existing service rejected an answer and returned no suggestion, the evaluator does not reconstruct hidden text. An artificial correctly recorded text that violates a domain rule is assessed as error and marked by its provenance.

## 8. How to accept this contract

This finite table is accepted as the E01 rules contract. Before quality_rules.py is implemented, a separate confirmation of the human labelling of the development part by E05 remains; the structural loader E04 depends only on the published format contract and may proceed earlier. The sources and the table are fixed by hashes. All word forms, exceptions and supported contexts are listed here; adding a new construction is a change of the contract, not a local adjustment to an independent example.

The checks of every row must include a positive control, a close wrong value or an unsupported context, and the expected difference. For normalization the preservation of the original range is also required. For a full answer the following scenarios are mandatory: a correct price plus an unknown property, a repeat of an equal price, a correct plus a wrong price, two products and a foreign price, an error in the hint with a correct customer reply, a domain prohibition inside a negation, an empty answer and the absence of a mandatory fact.

This document confirms neither 60 human references nor a 16/20 coverage. When the manual review share is exceeded, the independent acceptance is not passed; silently widening the table and reusing the same set as independent is forbidden.

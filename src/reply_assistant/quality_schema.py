"""Strict quality document models."""

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

# === Shared enums ===

SHA256_PATTERN = r'^[0-9a-f]{64}$'

Language = Literal['en', 'ru']
SourcePath = Literal['kb/example-en.yaml', 'kb/example-ru.yaml']
RulesId = Literal['factual-assessment-v1']
Predicate = Literal[
    'name',
    'form',
    'description',
    'price',
    'material',
    'form_kind',
    'container',
    'package_quantity',
    'portion_mass',
    'form_quantity',
    'batch_capacity',
    'section_count',
    'filter_size',
    'goes_with',
    'object_mass',
    'delivery',
    'stock',
    'treatment_result',
]
ValueType = Literal['text', 'decimal', 'integer', 'reference']
Unit = Literal['USD', 'RUB', 'g', 'ml', 'piece', 'section']
Derivation = Literal['literal', 'decimal', 'unit_alias', 'profile_component']
ReviewStatus = Literal['agent_prepared', 'human_confirmed']
ProfileId = Literal['F01', 'F02', 'F03', 'F04', 'F05', 'F06', 'F07', 'F08']
QuantityRole = Literal[
    'package_quantity',
    'portion_mass',
    'batch_capacity',
    'section_count',
    'unresolved',
]
SupportStatus = Literal['supported', 'absent', 'unresolved']
Topic = Literal['delivery', 'stock', 'treatment_result']
ClaimField = Literal['customer_reply', 'upsell_hint']
Stance = Literal['affirmed', 'unknown']
ActionKind = Literal['handoff', 'doctor']
KbMatch = Literal['found', 'partial', 'none']
ObservationOutcome = Literal['answer', 'provider_error', 'suggestion_rejected']
ObservationStage = Literal['model_output', 'final_suggestion']
OriginKind = Literal['agent_authored', 'human_authored', 'recorded', 'derived']
LabelStatus = Literal['pending', 'confirmed', 'disputed']
Verdict = Literal['correct', 'incorrect', 'unresolved']
Partition = Literal['development', 'holdout', 'examples']
Category = Literal[
    'price_currency',
    'form_quantity',
    'product_relations',
    'unsupported_facts',
    'completeness_hint',
]

# === Models ===


class _StrictModel(BaseModel):
    """Base of strict models."""

    model_config = ConfigDict(extra='forbid', strict=True)


class Source(_StrictModel):
    """Identify one public source."""

    id: str = Field(min_length=1)
    path: SourcePath
    sha256: str = Field(pattern=SHA256_PATTERN)
    language: Language


class Sources(_StrictModel):
    """Describe the source collection."""

    document_kind: Literal['quality_sources']
    schema_version: int = Field(ge=1, le=1)
    rules_id: RulesId
    rules_sha256: str = Field(pattern=SHA256_PATTERN)
    sources: list[Source] = Field(min_length=1)


class Evidence(_StrictModel):
    """Locate a source fragment."""

    pointer: str = Field(min_length=1)
    start: int = Field(ge=0)
    end: int = Field(ge=0)
    quote: str = Field(min_length=1)


class Fact(_StrictModel):
    """Describe one grounded value."""

    id: str = Field(min_length=1)
    predicate: Predicate
    value_type: ValueType
    value: str = Field(min_length=1)
    unit: Unit | None
    derivation: Derivation
    evidence: list[Evidence] = Field(min_length=1)


class Support(_StrictModel):
    """Describe a predicate boundary."""

    predicate: Predicate
    status: SupportStatus
    reason: str = Field(min_length=1)


class ProductFacts(_StrictModel):
    """Collect one product profile."""

    source_id: str = Field(min_length=1)
    product_id: str = Field(min_length=1)
    profile_id: ProfileId
    quantity_role: QuantityRole
    facts: list[Fact] = Field(min_length=1)
    predicate_support: list[Support] = Field(min_length=1)


class Facts(_StrictModel):
    """Describe catalogue annotations."""

    document_kind: Literal['quality_facts']
    schema_version: int = Field(ge=1, le=1)
    sources_sha256: str = Field(pattern=SHA256_PATTERN)
    review_status: ReviewStatus
    confirmation_ref: str | None = Field(min_length=1)
    products: list[ProductFacts] = Field(min_length=1)


class RequiredClaim(_StrictModel):
    """Describe one question obligation."""

    field: ClaimField
    product_id: str | None = Field(min_length=1)
    target_product_id: str | None = Field(min_length=1)
    predicate: Predicate
    stance: Stance


class RequiredAction(_StrictModel):
    """Describe a required action."""

    field: ClaimField
    kind: ActionKind


class Question(_StrictModel):
    """Describe the question contract."""

    id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    language: Language
    place: str | None = Field(min_length=1)
    topic: Topic | None
    required_claims: list[RequiredClaim]
    required_actions: list[RequiredAction]
    allowed_kb_matches: list[KbMatch] = Field(min_length=1)
    basis: str = Field(min_length=1)


class Questions(_StrictModel):
    """Collect question contracts."""

    document_kind: Literal['quality_questions']
    schema_version: int = Field(ge=1, le=1)
    sources_sha256: str = Field(pattern=SHA256_PATTERN)
    questions: list[Question] = Field(min_length=1)


class AssessmentQuestion(_StrictModel):
    """Assessment question projection."""

    source_id: str = Field(min_length=1)
    message: str = Field(min_length=1, max_length=2000)
    language: Language
    place: str | None = Field(min_length=1)
    topic: Topic | None
    required_claims: list[RequiredClaim]
    required_actions: list[RequiredAction]
    allowed_kb_matches: list[KbMatch] = Field(min_length=1)


class Answer(_StrictModel):
    """Keep the recorded answer."""

    customer_reply: str
    upsell_hint: str
    upsell_product_id: str | None
    kb_match: KbMatch


class Observation(_StrictModel):
    """Keep the recording outcome."""

    outcome: ObservationOutcome
    stage: ObservationStage | None
    answer: Answer | None
    error_code: str | None = Field(min_length=1)


class Generation(_StrictModel):
    """Preserve known generation metadata."""

    provider: str | None = Field(min_length=1)
    model: str | None = Field(min_length=1)
    max_output_tokens: int | None = Field(gt=0)
    temperature: str | None = Field(min_length=1)
    input_tokens: int | None = Field(ge=0)
    output_tokens: int | None = Field(ge=0)
    attempts: int | None = Field(gt=0)
    run_reference: str | None = Field(min_length=1)


class Origin(_StrictModel):
    """Declare one content origin."""

    kind: OriginKind
    reference: str | None = Field(min_length=1)
    sha256: str | None = Field(pattern=SHA256_PATTERN)
    parent_case_id: str | None = Field(min_length=1)
    record_pointer: str | None
    generation: Generation | None


class Label(_StrictModel):
    """Separate truth from proposals."""

    status: LabelStatus
    proposed_verdict: Verdict | None
    verdict: Verdict | None
    rationale: str
    evidence: list[Evidence]
    reviewed_by: str | None = Field(min_length=1)
    reviewed_at: str | None = Field(min_length=1)
    confirmation_ref: str | None = Field(min_length=1)


class Case(_StrictModel):
    """Collect one evaluation record."""

    id: str = Field(min_length=1)
    group_id: str = Field(min_length=1)
    question_id: str = Field(min_length=1)
    question_sha256: str = Field(pattern=SHA256_PATTERN)
    categories: list[Category] = Field(min_length=1)
    observation: Observation
    question_origin: Origin
    answer_origin: Origin
    label: Label


class Corpus(_StrictModel):
    """Describe an isolated partition."""

    document_kind: Literal['quality_corpus']
    schema_version: int = Field(ge=1, le=1)
    partition: Partition
    sources_sha256: str = Field(pattern=SHA256_PATTERN)
    facts_sha256: str = Field(pattern=SHA256_PATTERN)
    questions_sha256: str = Field(pattern=SHA256_PATTERN)
    cases: list[Case] = Field(min_length=1)


# === Document union ===

QualityDocument = Annotated[
    Sources | Facts | Questions | Corpus,
    Field(discriminator='document_kind'),
]

DOCUMENT_MODELS: tuple[type[BaseModel], ...] = (
    Answer,
    Case,
    Corpus,
    Evidence,
    Fact,
    Facts,
    Generation,
    Label,
    Observation,
    Origin,
    ProductFacts,
    Question,
    Questions,
    RequiredAction,
    RequiredClaim,
    Source,
    Sources,
    Support,
)

KNOWN_FIELD_NAMES = frozenset(
    {'quality_sources', 'quality_facts', 'quality_questions', 'quality_corpus'}
) | frozenset(field for model in DOCUMENT_MODELS for field in model.model_fields)

_DOCUMENT_ADAPTER: TypeAdapter['QualityDocument'] = TypeAdapter(QualityDocument)


def validate_quality_document(data: dict[str, Any]) -> QualityDocument:
    """Validate one decoded document."""
    return _DOCUMENT_ADAPTER.validate_python(data)

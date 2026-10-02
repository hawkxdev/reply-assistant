"""Loading of quality documents."""

import asyncio
import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from json import JSONDecodeError
from pathlib import Path
from typing import Any, NoReturn

import yaml
from pydantic import ValidationError

from reply_assistant.knowledge_base import KnowledgeBase, KnowledgeBaseError
from reply_assistant.knowledge_base import _document as validate_catalogue
from reply_assistant.quality_schema import (
    KNOWN_FIELD_NAMES,
    AssessmentQuestion,
    Case,
    Corpus,
    Evidence,
    Fact,
    Facts,
    Label,
    Observation,
    Origin,
    ProductFacts,
    QualityDocument,
    Question,
    Questions,
    Source,
    Sources,
    validate_quality_document,
)

# === Error ===


class QualityInputError(Exception):
    """Invalid quality document input."""

    def __init__(self, code: str, location: str | None = None) -> None:
        """Keep the safe code."""
        message = code if location is None else f'{code} at {location}'
        super().__init__(message)
        self.code = code
        self.location = location


# === Port ===


def read_quality_bytes(path: Path) -> bytes:
    """Read raw document bytes."""
    return path.read_bytes()


# === Decoding ===


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """Reject duplicate object keys."""
    mapping: dict[str, Any] = {}
    for key, value in pairs:
        if key in mapping:
            raise QualityInputError('duplicate_key')
        mapping[key] = value
    return mapping


def _reject_constant(name: str) -> NoReturn:
    """Reject one nonfinite constant."""
    raise QualityInputError('nonfinite_number')


def _decode_document(raw: bytes) -> Any:
    """Decode raw document bytes."""
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise QualityInputError('encoding') from None
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except JSONDecodeError:
        raise QualityInputError('json_syntax') from None


# === Validation ===


def _safe_location(error: ValidationError) -> str | None:
    """Build a safe location."""
    parts: list[str] = []
    for segment in error.errors()[0]['loc']:
        if isinstance(segment, int):
            parts.append(str(segment))
        else:
            parts.append(segment if segment in KNOWN_FIELD_NAMES else 'extra')
    return '.'.join(parts) if parts else None


def _structure_document(data: Any) -> QualityDocument:
    """Validate the decoded document."""
    if not isinstance(data, dict):
        raise QualityInputError('schema')
    version = data.get('schema_version')
    if isinstance(version, int) and not isinstance(version, bool) and version != 1:
        raise QualityInputError('unsupported_version')
    try:
        return validate_quality_document(data)
    except ValidationError as error:
        raise QualityInputError('schema', _safe_location(error)) from None


# === Loading ===


@dataclass(frozen=True)
class LoadedQualityDocument:
    """One document with digest."""

    document: QualityDocument
    sha256: str


async def load_quality_document(path: Path) -> LoadedQualityDocument:
    """Load one quality document."""
    try:
        raw = await asyncio.to_thread(read_quality_bytes, path)
    except OSError:
        raise QualityInputError('read_error') from None
    digest = hashlib.sha256(raw).hexdigest()
    data = _decode_document(raw)
    document = _structure_document(data)
    return LoadedQualityDocument(document=document, sha256=digest)


# === Package models ===


@dataclass(frozen=True)
class AssessmentInput:
    """Isolated assessment projection."""

    catalogue: KnowledgeBase
    product_facts: tuple[ProductFacts, ...]
    question: AssessmentQuestion
    observation: Observation


@dataclass(frozen=True)
class VerifiedCase:
    """One case with projection."""

    case: Case
    assessment: AssessmentInput


@dataclass(frozen=True)
class LoadedQualityPackage:
    """Verified documents and cases."""

    sources: Sources
    facts: Facts
    questions: Questions
    corpora: tuple[Corpus, ...]
    sources_sha256: str
    facts_sha256: str
    questions_sha256: str
    corpora_sha256: tuple[str, ...]
    cases: tuple[VerifiedCase, ...]


# === Catalogue decoding ===


def _decode_catalogue(raw: bytes) -> KnowledgeBase:
    """Validate one pinned catalogue."""
    try:
        data = yaml.safe_load(raw.decode('utf-8'))
    except (UnicodeDecodeError, yaml.YAMLError):
        raise QualityInputError('schema') from None
    try:
        return validate_catalogue(data)
    except KnowledgeBaseError:
        raise QualityInputError('schema') from None


# === Identity checks ===


def _check_sources_identity(sources: Sources) -> None:
    """Check unique source identity."""
    ids: set[str] = set()
    paths: set[str] = set()
    for index, source in enumerate(sources.sources):
        if source.id in ids:
            raise QualityInputError('duplicate_id', f'sources.{index}.id')
        if source.path in paths:
            raise QualityInputError('duplicate_id', f'sources.{index}.path')
        ids.add(source.id)
        paths.add(source.path)


def _check_annotations_identity(facts: Facts, source_ids: frozenset[str]) -> None:
    """Check annotation identity."""
    pairs: set[tuple[str, str]] = set()
    for index, profile in enumerate(facts.products):
        if profile.source_id not in source_ids:
            raise QualityInputError('unknown_reference', f'products.{index}.source_id')
        pair = (profile.source_id, profile.product_id)
        if pair in pairs:
            raise QualityInputError('duplicate_id', f'products.{index}.product_id')
        pairs.add(pair)
        fact_ids: set[str] = set()
        for fact_index, fact in enumerate(profile.facts):
            if fact.id in fact_ids:
                raise QualityInputError(
                    'duplicate_id', f'products.{index}.facts.{fact_index}.id'
                )
            fact_ids.add(fact.id)


def _check_questions_identity(questions: Questions, source_ids: frozenset[str]) -> None:
    """Check question identity."""
    ids: set[str] = set()
    for index, question in enumerate(questions.questions):
        if question.id in ids:
            raise QualityInputError('duplicate_id', f'questions.{index}.id')
        if question.source_id not in source_ids:
            raise QualityInputError('unknown_reference', f'questions.{index}.source_id')
        ids.add(question.id)


def _check_cases_identity(
    corpora: Sequence[Corpus], question_ids: frozenset[str]
) -> dict[str, tuple[Corpus, Case]]:
    """Check case identity."""
    records: dict[str, tuple[Corpus, Case]] = {}
    for corpus_index, corpus in enumerate(corpora):
        for case_index, case in enumerate(corpus.cases):
            base = f'corpora.{corpus_index}.cases.{case_index}'
            if case.question_id not in question_ids:
                raise QualityInputError('unknown_reference', f'{base}.question_id')
            if len(set(case.categories)) != len(case.categories):
                raise QualityInputError('duplicate_id', f'{base}.categories')
            if case.id in records:
                raise QualityInputError('duplicate_id', f'{base}.id')
            records[case.id] = (corpus, case)
    return records


# === Lineage checks ===


def _lineage_parent(case: Case, answer: bool) -> str | None:
    """Return one derived lineage parent."""
    origin = case.answer_origin if answer else case.question_origin
    if origin.kind != 'derived':
        return None
    return origin.parent_case_id


def _check_lineage(records: dict[str, tuple[Corpus, Case]]) -> None:
    """Check derived references."""
    for corpus, case in records.values():
        for origin in (case.question_origin, case.answer_origin):
            if origin.kind != 'derived':
                continue
            parent_id = origin.parent_case_id
            if parent_id is None:
                continue
            if parent_id not in records:
                raise QualityInputError('unknown_reference', 'parent_case_id')
            parent_corpus, parent_case = records[parent_id]
            if (
                parent_case.group_id != case.group_id
                or parent_corpus.partition != corpus.partition
            ):
                raise QualityInputError('unknown_reference', 'parent_case_id')
    for _, case in records.values():
        for answer in (False, True):
            visited = {case.id}
            parent_id = _lineage_parent(case, answer)
            while parent_id is not None:
                if parent_id in visited:
                    raise QualityInputError('lineage_cycle', 'parent_case_id')
                visited.add(parent_id)
                parent_id = _lineage_parent(records[parent_id][1], answer)


# === Source verification ===


def _check_source_paths(project_root: Path, sources: Sources) -> None:
    """Check safe source paths."""
    for index, source in enumerate(sources.sources):
        current = project_root
        for part in Path(source.path).parts:
            current = current / part
            if current.is_symlink():
                raise QualityInputError('source_path', f'sources.{index}.path')


async def _verify_source(
    project_root: Path, source: Source, index: int
) -> KnowledgeBase:
    """Read and verify one source."""
    location = f'sources.{index}.sha256'
    try:
        raw = await asyncio.to_thread(read_quality_bytes, project_root / source.path)
    except OSError:
        raise QualityInputError('read_error', location) from None
    if hashlib.sha256(raw).hexdigest() != source.sha256:
        raise QualityInputError('source_hash', location)
    catalogue = await asyncio.to_thread(_decode_catalogue, raw)
    if catalogue.language != source.language:
        raise QualityInputError('source_hash', location)
    return catalogue


# === Reference checks ===


def _check_product_references(
    facts: Facts,
    questions: Questions,
    product_ids: dict[str, frozenset[str]],
) -> None:
    """Check product references."""
    for index, profile in enumerate(facts.products):
        known = product_ids[profile.source_id]
        if profile.product_id not in known:
            raise QualityInputError('unknown_reference', f'products.{index}.product_id')
        for fact_index, fact in enumerate(profile.facts):
            if fact.predicate == 'goes_with' and fact.value not in known:
                raise QualityInputError(
                    'unknown_reference', f'products.{index}.facts.{fact_index}.value'
                )
    for index, question in enumerate(questions.questions):
        known = product_ids[question.source_id]
        for claim_index, claim in enumerate(question.required_claims):
            base = f'questions.{index}.required_claims.{claim_index}'
            if claim.predicate == 'goes_with' and (
                claim.product_id is None or claim.target_product_id is None
            ):
                raise QualityInputError('unknown_reference', base)
            if claim.product_id is not None and claim.product_id not in known:
                raise QualityInputError('unknown_reference', f'{base}.product_id')
            if (
                claim.target_product_id is not None
                and claim.target_product_id not in known
            ):
                raise QualityInputError(
                    'unknown_reference', f'{base}.target_product_id'
                )


# === Binding checks ===


def _question_digest(question: Question) -> str:
    """Hash one canonical question."""
    payload = question.model_dump(mode='json')
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _check_bindings(
    facts: Facts,
    questions: Questions,
    corpora: Sequence[Corpus],
    sources_sha256: str,
    facts_sha256: str,
    questions_sha256: str,
    questions_by_id: dict[str, Question],
) -> None:
    """Check pinned document bindings."""
    if facts.sources_sha256 != sources_sha256:
        raise QualityInputError('binding_hash', 'facts.sources_sha256')
    if questions.sources_sha256 != sources_sha256:
        raise QualityInputError('binding_hash', 'questions.sources_sha256')
    for corpus_index, corpus in enumerate(corpora):
        if corpus.sources_sha256 != sources_sha256:
            raise QualityInputError(
                'binding_hash', f'corpora.{corpus_index}.sources_sha256'
            )
        if corpus.facts_sha256 != facts_sha256:
            raise QualityInputError(
                'binding_hash', f'corpora.{corpus_index}.facts_sha256'
            )
        if corpus.questions_sha256 != questions_sha256:
            raise QualityInputError(
                'binding_hash', f'corpora.{corpus_index}.questions_sha256'
            )
        for case_index, case in enumerate(corpus.cases):
            question = questions_by_id[case.question_id]
            if case.question_sha256 != _question_digest(question):
                raise QualityInputError(
                    'question_hash',
                    f'corpora.{corpus_index}.cases.{case_index}.question_sha256',
                )


# === Evidence checks ===

_PRODUCT_FIELD_POINTER = re.compile(
    r'^/products/(0|[1-9][0-9]*)/(id|name|form|price|description)$'
)
_PRODUCT_EDGE_POINTER = re.compile(
    r'^/products/(0|[1-9][0-9]*)/goes_with/(0|[1-9][0-9]*)$'
)
_REPLY_RULE_POINTER = re.compile(r'^/reply_rules/(0|[1-9][0-9]*)$')


def _evidence_leaf(
    catalogue: KnowledgeBase, evidence: Evidence
) -> tuple[str, int | None]:
    """Resolve one evidence pointer."""
    pointer = evidence.pointer
    field_match = _PRODUCT_FIELD_POINTER.match(pointer)
    if field_match is not None:
        index = int(field_match.group(1))
        if index >= len(catalogue.products):
            raise QualityInputError('invalid_evidence', pointer)
        product = catalogue.products[index]
        return str(getattr(product, field_match.group(2))), index
    edge_match = _PRODUCT_EDGE_POINTER.match(pointer)
    if edge_match is not None:
        index = int(edge_match.group(1))
        if index >= len(catalogue.products):
            raise QualityInputError('invalid_evidence', pointer)
        edges = catalogue.products[index].goes_with
        edge_index = int(edge_match.group(2))
        if edge_index >= len(edges):
            raise QualityInputError('invalid_evidence', pointer)
        return edges[edge_index], index
    rule_match = _REPLY_RULE_POINTER.match(pointer)
    if rule_match is not None:
        index = int(rule_match.group(1))
        if index >= len(catalogue.reply_rules):
            raise QualityInputError('invalid_evidence', pointer)
        return catalogue.reply_rules[index], None
    if pointer == '/disclaimer' and catalogue.disclaimer is not None:
        return catalogue.disclaimer, None
    raise QualityInputError('invalid_evidence', pointer)


def _check_evidence(
    catalogue: KnowledgeBase, evidence: Evidence, product_index: int
) -> None:
    """Check one evidence span."""
    leaf, pointer_product = _evidence_leaf(catalogue, evidence)
    if pointer_product is not None and pointer_product != product_index:
        raise QualityInputError('invalid_evidence', evidence.pointer)
    if not 0 <= evidence.start < evidence.end <= len(leaf):
        raise QualityInputError('invalid_evidence', evidence.pointer)
    if leaf[evidence.start : evidence.end] != evidence.quote:
        raise QualityInputError('invalid_evidence', evidence.pointer)


# === Fact checks ===

_QUANTITY_UNITS: dict[str, frozenset[str]] = {
    'package_quantity': frozenset({'g', 'ml', 'piece'}),
    'form_quantity': frozenset({'g', 'ml', 'piece'}),
    'batch_capacity': frozenset({'g', 'ml'}),
    'portion_mass': frozenset({'g'}),
    'object_mass': frozenset({'g'}),
    'section_count': frozenset({'section'}),
}
_DECIMAL_VALUE = re.compile(r'^(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$')
_INTEGER_VALUE = re.compile(r'^[1-9][0-9]*$')


def _check_fact_shape(fact: Fact, location: str) -> None:
    """Check one typed fact."""
    if fact.predicate == 'price':
        consistent = (
            fact.value_type == 'decimal'
            and fact.unit in ('USD', 'RUB')
            and fact.derivation == 'decimal'
            and _DECIMAL_VALUE.fullmatch(fact.value) is not None
        )
    elif fact.predicate in _QUANTITY_UNITS:
        consistent = (
            fact.value_type == 'integer'
            and fact.unit in _QUANTITY_UNITS[fact.predicate]
            and fact.derivation == 'unit_alias'
            and _INTEGER_VALUE.fullmatch(fact.value) is not None
        )
    elif fact.predicate == 'goes_with':
        consistent = (
            fact.value_type == 'reference'
            and fact.unit is None
            and fact.derivation == 'literal'
        )
    elif fact.predicate == 'material':
        consistent = (
            fact.value_type == 'text'
            and fact.unit is None
            and fact.derivation in ('literal', 'profile_component')
        )
    else:
        consistent = (
            fact.value_type == 'text'
            and fact.unit is None
            and fact.derivation == 'literal'
        )
    if not consistent:
        raise QualityInputError('inconsistent_fact', location)


def _check_edges(profile: ProductFacts, edges: list[str], location: str) -> None:
    """Check complete relation facts."""
    values = sorted(
        fact.value for fact in profile.facts if fact.predicate == 'goes_with'
    )
    if values != sorted(edges):
        raise QualityInputError('inconsistent_fact', location)


def _check_support(profile: ProductFacts, edges: list[str]) -> None:
    """Check predicate support."""
    fact_counts: dict[str, int] = {}
    for fact in profile.facts:
        fact_counts[fact.predicate] = fact_counts.get(fact.predicate, 0) + 1
    statuses: dict[str, str] = {}
    for entry in profile.predicate_support:
        if entry.predicate in statuses:
            raise QualityInputError('inconsistent_fact', 'predicate_support')
        statuses[entry.predicate] = entry.status
    expected = 'supported' if edges else 'absent'
    if statuses.get('goes_with') != expected:
        raise QualityInputError('inconsistent_fact', 'predicate_support.goes_with')
    for predicate, status in statuses.items():
        if predicate == 'goes_with':
            continue
        count = fact_counts.get(predicate, 0)
        if status == 'supported' and count == 0:
            raise QualityInputError(
                'inconsistent_fact', f'predicate_support.{predicate}'
            )
        if status != 'supported' and count > 0:
            raise QualityInputError(
                'inconsistent_fact', f'predicate_support.{predicate}'
            )


# === Cross-field checks ===

_PROVIDER_ERROR_CODES = frozenset(
    {'timeout', 'connection', 'rate_limit', 'server', 'unknown'}
)
_REJECTION_CODES = frozenset(
    {'shape', 'product_exists', 'no_forbidden_claim', 'unknown'}
)


def _check_observation(observation: Observation, location: str) -> None:
    """Check one observation matrix."""
    if observation.outcome == 'answer':
        if (
            observation.stage is None
            or observation.answer is None
            or observation.error_code is not None
        ):
            raise QualityInputError('invalid_observation', location)
        return
    codes = (
        _PROVIDER_ERROR_CODES
        if observation.outcome == 'provider_error'
        else _REJECTION_CODES
    )
    if (
        observation.stage is not None
        or observation.answer is not None
        or observation.error_code not in codes
    ):
        raise QualityInputError('invalid_observation', location)


def _utc_timestamp(value: str) -> bool:
    """Check one UTC timestamp."""
    if not value.endswith('Z'):
        return False
    try:
        datetime.fromisoformat(f'{value[:-1]}+00:00')
    except ValueError:
        return False
    return True


def _check_label(label: Label, location: str) -> None:
    """Check one label matrix."""
    if label.status == 'pending':
        if (
            label.verdict is not None
            or label.reviewed_by is not None
            or label.reviewed_at is not None
            or label.confirmation_ref is not None
        ):
            raise QualityInputError('invalid_label', location)
        return
    if (
        label.reviewed_by is None
        or label.reviewed_at is None
        or not _utc_timestamp(label.reviewed_at)
        or label.confirmation_ref is None
        or label.rationale == ''
    ):
        raise QualityInputError('invalid_label', location)
    if label.status == 'confirmed':
        if label.verdict is None:
            raise QualityInputError('invalid_label', location)
    elif label.verdict != 'unresolved':
        raise QualityInputError('invalid_label', location)


def _check_origin(origin: Origin, answer: bool, location: str) -> None:
    """Check one origin matrix."""
    if origin.kind == 'recorded':
        if (
            origin.reference is None
            or origin.sha256 is None
            or origin.record_pointer is None
            or origin.parent_case_id is not None
            or (answer and origin.generation is None)
            or (not answer and origin.generation is not None)
        ):
            raise QualityInputError('invalid_label', location)
    elif origin.kind == 'derived':
        if (
            origin.parent_case_id is None
            or origin.record_pointer is not None
            or origin.generation is not None
        ):
            raise QualityInputError('invalid_label', location)
    else:
        if (
            origin.record_pointer is not None
            or origin.generation is not None
            or (origin.reference is None) != (origin.sha256 is None)
        ):
            raise QualityInputError('invalid_label', location)


# === Partition checks ===


def _check_partitions(corpora: Sequence[Corpus]) -> None:
    """Check group partition isolation."""
    partitions: dict[str, str] = {}
    for corpus_index, corpus in enumerate(corpora):
        for case in corpus.cases:
            seen = partitions.setdefault(case.group_id, corpus.partition)
            if seen != corpus.partition:
                raise QualityInputError(
                    'split_leakage', f'corpora.{corpus_index}.partition'
                )


# === Package loading ===


def _case_location(corpus_index: int, case_index: int, field: str) -> str:
    """Build one safe case location."""
    return f'corpora.{corpus_index}.cases.{case_index}.{field}'


async def load_quality_package(
    project_root: Path,
    sources: Path,
    facts: Path,
    questions: Path,
    corpora: Sequence[Path],
) -> LoadedQualityPackage:
    """Load one verified package."""
    # Step 1: read and structurally validate every document.
    sources_loaded = await load_quality_document(sources)
    facts_loaded = await load_quality_document(facts)
    questions_loaded = await load_quality_document(questions)
    corpora_loaded = [await load_quality_document(path) for path in corpora]
    if not isinstance(sources_loaded.document, Sources):
        raise QualityInputError('schema', 'sources.document_kind')
    if not isinstance(facts_loaded.document, Facts):
        raise QualityInputError('schema', 'facts.document_kind')
    if not isinstance(questions_loaded.document, Questions):
        raise QualityInputError('schema', 'questions.document_kind')
    sources_document = sources_loaded.document
    facts_document = facts_loaded.document
    questions_document = questions_loaded.document
    corpus_documents: list[Corpus] = []
    for index, loaded in enumerate(corpora_loaded):
        if not isinstance(loaded.document, Corpus):
            raise QualityInputError('schema', f'corpora.{index}.document_kind')
        corpus_documents.append(loaded.document)

    # Step 2: check identity and references between documents.
    _check_sources_identity(sources_document)
    source_ids = frozenset(source.id for source in sources_document.sources)
    _check_annotations_identity(facts_document, source_ids)
    _check_questions_identity(questions_document, source_ids)
    questions_by_id = {
        question.id: question for question in questions_document.questions
    }
    records = _check_cases_identity(corpus_documents, frozenset(questions_by_id))
    _check_lineage(records)

    # Step 3: verify source paths then pinned catalogue bytes.
    _check_source_paths(project_root, sources_document)
    catalogues: dict[str, KnowledgeBase] = {}
    product_ids: dict[str, frozenset[str]] = {}
    product_indexes: dict[str, dict[str, int]] = {}
    for index, source in enumerate(sources_document.sources):
        catalogue = await _verify_source(project_root, source, index)
        catalogues[source.id] = catalogue
        product_ids[source.id] = frozenset(product.id for product in catalogue.products)
        product_indexes[source.id] = {
            product.id: position for position, product in enumerate(catalogue.products)
        }
    _check_product_references(facts_document, questions_document, product_ids)

    # Step 4: check pinned document and question bindings.
    _check_bindings(
        facts_document,
        questions_document,
        corpus_documents,
        sources_loaded.sha256,
        facts_loaded.sha256,
        questions_loaded.sha256,
        questions_by_id,
    )

    # Step 5: check evidence spans and typed fact support.
    for index, profile in enumerate(facts_document.products):
        catalogue = catalogues[profile.source_id]
        product_index = product_indexes[profile.source_id][profile.product_id]
        for fact_index, fact in enumerate(profile.facts):
            for evidence in fact.evidence:
                _check_evidence(catalogue, evidence, product_index)
            _check_fact_shape(fact, f'products.{index}.facts.{fact_index}')
        edges = catalogue.products[product_index].goes_with
        _check_edges(profile, edges, f'products.{index}.facts')
        _check_support(profile, edges)

    # Step 6: check observation, label and origin matrices.
    for corpus_index, corpus in enumerate(corpus_documents):
        for case_index, case in enumerate(corpus.cases):
            observation_location = _case_location(
                corpus_index, case_index, 'observation'
            )
            _check_observation(case.observation, observation_location)
            _check_label(case.label, _case_location(corpus_index, case_index, 'label'))
            _check_origin(
                case.question_origin,
                False,
                _case_location(corpus_index, case_index, 'question_origin'),
            )
            _check_origin(
                case.answer_origin,
                True,
                _case_location(corpus_index, case_index, 'answer_origin'),
            )

    # Step 7: check partition isolation and build projections.
    _check_partitions(corpus_documents)
    annotations = {
        source_id: tuple(
            profile
            for profile in facts_document.products
            if profile.source_id == source_id
        )
        for source_id in catalogues
    }
    verified: list[VerifiedCase] = []
    for corpus in corpus_documents:
        for case in corpus.cases:
            question = questions_by_id[case.question_id]
            projection = AssessmentQuestion.model_validate(
                question.model_dump(exclude={'id', 'basis'})
            )
            verified.append(
                VerifiedCase(
                    case=case,
                    assessment=AssessmentInput(
                        catalogue=catalogues[question.source_id],
                        product_facts=annotations[question.source_id],
                        question=projection,
                        observation=case.observation,
                    ),
                )
            )
    return LoadedQualityPackage(
        sources=sources_document,
        facts=facts_document,
        questions=questions_document,
        corpora=tuple(corpus_documents),
        sources_sha256=sources_loaded.sha256,
        facts_sha256=facts_loaded.sha256,
        questions_sha256=questions_loaded.sha256,
        corpora_sha256=tuple(loaded.sha256 for loaded in corpora_loaded),
        cases=tuple(verified),
    )

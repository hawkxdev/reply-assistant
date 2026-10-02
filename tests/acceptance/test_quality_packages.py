"""Acceptance for issue 61."""

import hashlib
import importlib
import json
import threading
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

# === Data ===

ROOT = Path(__file__).parents[2]
DATA = ROOT / 'evals' / 'quality' / 'v1'
ZERO = '0' * 64

# === Fixtures and helpers ===


@pytest.fixture
def loader() -> ModuleType:
    """Import the package loader."""
    return importlib.import_module('reply_assistant.quality_corpus')


def load_payload(relative: str) -> dict[str, Any]:
    """Read one supplied document."""
    text = (DATA / relative).read_text(encoding='utf-8')
    return cast(dict[str, Any], json.loads(text))


def sources_payload() -> dict[str, Any]:
    """Return fresh sources payload."""
    return load_payload('sources.json')


def facts_payload() -> dict[str, Any]:
    """Return fresh facts payload."""
    return load_payload('facts.json')


def questions_payload() -> dict[str, Any]:
    """Return fresh questions payload."""
    return load_payload('examples/questions.json')


def corpus_payload() -> dict[str, Any]:
    """Return fresh corpus payload."""
    return load_payload('examples/corpus-valid.json')


def canonical_question_sha(question: dict[str, Any]) -> str:
    """Hash one canonical question."""
    encoded = json.dumps(
        question,
        ensure_ascii=False,
        sort_keys=True,
        separators=(',', ':'),
        allow_nan=False,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def write_json(folder: Path, name: str, payload: dict[str, Any]) -> str:
    """Write one document payload."""
    raw = json.dumps(payload, ensure_ascii=False, indent=2).encode('utf-8')
    (folder / name).write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def build_package(
    folder: Path,
    sources: dict[str, Any] | None = None,
    facts: dict[str, Any] | None = None,
    questions: dict[str, Any] | None = None,
    corpora: list[dict[str, Any]] | None = None,
    with_catalogues: bool = True,
) -> tuple[Path, Path, Path, tuple[Path, ...]]:
    """Write one full package."""
    if with_catalogues:
        catalogue_folder = folder / 'kb'
        catalogue_folder.mkdir()
        for name in ('example-en.yaml', 'example-ru.yaml'):
            raw = (ROOT / 'kb' / name).read_bytes()
            (catalogue_folder / name).write_bytes(raw)
    sources = sources if sources is not None else sources_payload()
    facts = facts if facts is not None else facts_payload()
    questions = questions if questions is not None else questions_payload()
    corpora = corpora if corpora is not None else [corpus_payload()]

    sources_digest = write_json(folder, 'sources.json', sources)
    facts['sources_sha256'] = sources_digest
    facts_digest = write_json(folder, 'facts.json', facts)
    questions['sources_sha256'] = sources_digest
    questions_digest = write_json(folder, 'questions.json', questions)
    question_hashes = {
        cast(str, question['id']): canonical_question_sha(question)
        for question in questions['questions']
    }
    for corpus in corpora:
        corpus['sources_sha256'] = sources_digest
        corpus['facts_sha256'] = facts_digest
        corpus['questions_sha256'] = questions_digest
        for case in corpus['cases']:
            case['question_sha256'] = question_hashes.get(
                cast(str, case['question_id']), ZERO
            )
    corpus_paths = []
    for index, corpus in enumerate(corpora):
        write_json(folder, f'corpus-{index}.json', corpus)
        corpus_paths.append(folder / f'corpus-{index}.json')
    return (
        folder / 'sources.json',
        folder / 'facts.json',
        folder / 'questions.json',
        tuple(corpus_paths),
    )


async def failed_code(
    loader: ModuleType,
    paths: tuple[Path, Path, Path, tuple[Path, ...]],
) -> Any:
    """Load expecting one failure."""
    sources, facts, questions, corpora = paths
    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_package(
            sources.parent, sources, facts, questions, list(corpora)
        )
    return caught.value


def rewrite_document(folder: Path, name: str) -> None:
    """Rewrite one document differently."""
    path = folder / name
    payload = cast(dict[str, Any], json.loads(path.read_text(encoding='utf-8')))
    path.write_text(json.dumps(payload, indent=1), encoding='utf-8')


def case_of(corpus: dict[str, Any]) -> dict[str, Any]:
    """Return the single case."""
    return cast(dict[str, Any], corpus['cases'][0])


def copy_case(case: dict[str, Any]) -> dict[str, Any]:
    """Deep copy one case."""
    return cast(dict[str, Any], json.loads(json.dumps(case)))


def derived_origin(parent: str | None) -> dict[str, Any]:
    """Build one derived origin."""
    return {
        'kind': 'derived',
        'reference': None,
        'sha256': None,
        'parent_case_id': parent,
        'record_pointer': None,
        'generation': None,
    }


# === Supplied set ===


async def test_supplied_set_loads_end_to_end(loader: ModuleType) -> None:
    package = await loader.load_quality_package(
        ROOT,
        DATA / 'sources.json',
        DATA / 'facts.json',
        DATA / 'examples/questions.json',
        [DATA / 'examples' / 'corpus-valid.json'],
    )

    assert len(package.cases) == 1
    assert package.cases[0].case.id == 'example-case-price'


async def test_projection_exposes_assessment_content_only(loader: ModuleType) -> None:
    package = await loader.load_quality_package(
        ROOT,
        DATA / 'sources.json',
        DATA / 'facts.json',
        DATA / 'examples/questions.json',
        [DATA / 'examples' / 'corpus-valid.json'],
    )
    assessment = package.cases[0].assessment
    question = assessment.question
    observation = assessment.observation

    assert assessment.catalogue.company == 'Clayfield Minerals'
    assert assessment.catalogue.language == 'en'
    assert assessment.catalogue.products[0].id == 'zeolite-powder-200'
    assert len(assessment.product_facts) == 5
    product_ids = {item.product_id for item in assessment.product_facts}
    assert product_ids == {
        'zeolite-powder-200',
        'zeolite-capsules-90',
        'clay-face-mask-100',
        'measuring-spoon',
        'travel-pill-box',
    }
    assert question.message == 'What is the price of Zeolite Powder?'
    assert not hasattr(question, 'id')
    assert not hasattr(question, 'basis')
    assert observation.stage == 'model_output'
    assert observation.answer.customer_reply == 'Zeolite Powder costs 18.00 USD.'
    for name in (
        'case',
        'case_id',
        'group_id',
        'categories',
        'partition',
        'label',
        'question_origin',
        'answer_origin',
        'filename',
    ):
        assert not hasattr(assessment, name)


async def test_projection_keeps_unknown_upsell_id_as_data(
    loader: ModuleType, tmp_path: Path
) -> None:
    corpus = corpus_payload()
    case_of(corpus)['observation']['answer']['upsell_product_id'] = (
        'not-a-catalogue-product'
    )
    paths = build_package(tmp_path, corpora=[corpus])
    package = await loader.load_quality_package(tmp_path, *paths[:3], list(paths[3]))

    answer = package.cases[0].assessment.observation.answer
    assert answer.upsell_product_id == 'not-a-catalogue-product'


async def test_recorded_failure_remains_a_case(
    loader: ModuleType, tmp_path: Path
) -> None:
    corpus = corpus_payload()
    case_of(corpus)['observation'] = {
        'outcome': 'provider_error',
        'stage': None,
        'answer': None,
        'error_code': 'timeout',
    }
    case_of(corpus)['answer_origin'] = {
        'kind': 'recorded',
        'reference': 'runs/r1.json',
        'sha256': ZERO,
        'parent_case_id': None,
        'record_pointer': '',
        'generation': {
            'provider': None,
            'model': None,
            'max_output_tokens': 1,
            'temperature': None,
            'input_tokens': 0,
            'output_tokens': 0,
            'attempts': 1,
            'run_reference': None,
        },
    }
    paths = build_package(tmp_path, corpora=[corpus])
    package = await loader.load_quality_package(tmp_path, *paths[:3], list(paths[3]))
    observation = package.cases[0].assessment.observation

    assert observation.outcome == 'provider_error'
    assert observation.answer is None
    assert observation.error_code == 'timeout'


# === Pins and sources ===


async def test_binding_example_fails_with_binding_hash(loader: ModuleType) -> None:
    with pytest.raises(loader.QualityInputError) as caught:
        await loader.load_quality_package(
            ROOT,
            DATA / 'sources.json',
            DATA / 'facts.json',
            DATA / 'examples/questions.json',
            [DATA / 'examples' / 'corpus-invalid-binding.json'],
        )

    assert caught.value.code == 'binding_hash'


@pytest.mark.parametrize(
    ('defect', 'code'),
    [
        ('sources-bytes', 'binding_hash'),
        ('facts-bytes', 'binding_hash'),
        ('questions-bytes', 'binding_hash'),
        ('question-pin', 'question_hash'),
    ],
    ids=['sources', 'facts', 'questions', 'question'],
)
async def test_pin_mutations_fail_with_hash_codes(
    loader: ModuleType, tmp_path: Path, defect: str, code: str
) -> None:
    if defect == 'question-pin':
        paths = build_package(tmp_path)
        corpus = cast(dict[str, Any], json.loads(paths[3][0].read_text()))
        case_of(corpus)['question_sha256'] = ZERO
        paths[3][0].write_text(json.dumps(corpus), encoding='utf-8')
    else:
        paths = build_package(tmp_path)
        name = {
            'sources-bytes': 'sources.json',
            'facts-bytes': 'facts.json',
            'questions-bytes': 'questions.json',
        }[defect]
        rewrite_document(tmp_path, name)

    assert (await failed_code(loader, paths)).code == code


async def test_changed_catalogue_fails_with_source_hash(
    loader: ModuleType, tmp_path: Path
) -> None:
    paths = build_package(tmp_path)
    catalogue = tmp_path / 'kb' / 'example-en.yaml'
    catalogue.write_bytes(catalogue.read_bytes() + b'\n# changed\n')

    assert (await failed_code(loader, paths)).code == 'source_hash'


@pytest.mark.parametrize(
    ('defect', 'code'),
    [
        ('absolute', 'schema'),
        ('traversal', 'schema'),
        ('uri', 'schema'),
        ('symlink', 'source_path'),
    ],
)
async def test_source_paths_reject_before_read(
    loader: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    defect: str,
    code: str,
) -> None:
    sources = sources_payload()
    catalogue = str(ROOT / 'kb' / 'example-en.yaml')
    sources['sources'][0]['path'] = {
        'absolute': catalogue,
        'traversal': '../kb/example-en.yaml',
        'uri': f'file://{catalogue}',
        'symlink': 'kb/example-en.yaml',
    }[defect]
    if defect == 'symlink':
        (tmp_path / 'kb-target').mkdir()
        (tmp_path / 'kb').symlink_to(tmp_path / 'kb-target')
    paths = build_package(tmp_path, sources=sources, with_catalogues=False)
    reads: list[Path] = []
    original = loader.read_quality_bytes

    def observe_read(path: Path) -> bytes:
        """Observe one read."""
        reads.append(path)
        result = original(path)
        assert isinstance(result, bytes)
        return result

    monkeypatch.setattr(loader, 'read_quality_bytes', observe_read)

    assert (await failed_code(loader, paths)).code == code
    assert all(not read.name.startswith('example-') for read in reads)


async def test_source_resolution_ignores_process_cwd(
    loader: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    package = await loader.load_quality_package(
        ROOT,
        DATA / 'sources.json',
        DATA / 'facts.json',
        DATA / 'examples/questions.json',
        [DATA / 'examples' / 'corpus-valid.json'],
    )

    assert package.cases[0].case.id == 'example-case-price'


# === Identity and references ===


@pytest.mark.parametrize(
    'defect',
    [
        'case-id',
        'question-id',
        'source-id',
        'source-path',
        'product-pair',
        'fact-id',
        'category',
    ],
)
async def test_duplicate_identity_fails(
    loader: ModuleType, tmp_path: Path, defect: str
) -> None:
    if defect == 'case-id':
        corpus = corpus_payload()
        corpus['cases'].append(copy_case(case_of(corpus)))
        paths = build_package(tmp_path, corpora=[corpus])
    elif defect == 'question-id':
        questions = questions_payload()
        questions['questions'].append(copy_case(questions['questions'][0]))
        paths = build_package(tmp_path, questions=questions)
    elif defect == 'source-id':
        sources = sources_payload()
        sources['sources'].append(copy_case(sources['sources'][0]))
        paths = build_package(tmp_path, sources=sources)
    elif defect == 'source-path':
        sources = sources_payload()
        extra = copy_case(sources['sources'][0])
        extra['id'] = 'public-extra'
        sources['sources'].append(extra)
        paths = build_package(tmp_path, sources=sources)
    elif defect == 'product-pair':
        facts = facts_payload()
        facts['products'].append(copy_case(facts['products'][0]))
        paths = build_package(tmp_path, facts=facts)
    elif defect == 'fact-id':
        facts = facts_payload()
        powder = facts['products'][0]
        powder['facts'].append(copy_case(powder['facts'][0]))
        paths = build_package(tmp_path, facts=facts)
    else:
        corpus = corpus_payload()
        case_of(corpus)['categories'] = ['price_currency', 'price_currency']
        paths = build_package(tmp_path, corpora=[corpus])

    assert (await failed_code(loader, paths)).code == 'duplicate_id'


@pytest.mark.parametrize(
    'defect',
    ['question', 'claim-product', 'claim-target', 'edge-target', 'derived-parent'],
)
async def test_unknown_references_fail(
    loader: ModuleType, tmp_path: Path, defect: str
) -> None:
    if defect == 'question':
        corpus = corpus_payload()
        case_of(corpus)['question_id'] = 'no-such-question'
        paths = build_package(tmp_path, corpora=[corpus])
    elif defect == 'claim-product':
        questions = questions_payload()
        questions['questions'][0]['required_claims'][0]['product_id'] = (
            'no-such-product'
        )
        paths = build_package(tmp_path, questions=questions)
    elif defect == 'claim-target':
        questions = questions_payload()
        first_claim = questions['questions'][0]['required_claims'][0]
        first_claim['target_product_id'] = 'no-such-product'
        paths = build_package(tmp_path, questions=questions)
    elif defect == 'edge-target':
        facts = facts_payload()
        facts['products'][0]['facts'][7]['value'] = 'no-such-product'
        paths = build_package(tmp_path, facts=facts)
    else:
        corpus = corpus_payload()
        case_of(corpus)['answer_origin'] = derived_origin('ghost-case')
        paths = build_package(tmp_path, corpora=[corpus])

    assert (await failed_code(loader, paths)).code == 'unknown_reference'


async def test_derived_lineage_cycle_fails(loader: ModuleType, tmp_path: Path) -> None:
    corpus = corpus_payload()
    second = copy_case(case_of(corpus))
    second['id'] = 'case-b'
    case_of(corpus)['answer_origin'] = derived_origin('case-b')
    second['answer_origin'] = derived_origin('example-case-price')
    corpus['cases'].append(second)
    paths = build_package(tmp_path, corpora=[corpus])

    assert (await failed_code(loader, paths)).code == 'lineage_cycle'


# === Evidence and facts ===


@pytest.mark.parametrize('defect', ['pointer', 'range', 'equal', 'quote', 'foreign'])
async def test_evidence_violations_fail(
    loader: ModuleType, tmp_path: Path, defect: str
) -> None:
    facts = facts_payload()
    evidence = facts['products'][0]['facts'][0]['evidence'][0]
    if defect == 'pointer':
        evidence['pointer'] = '/company'
    elif defect == 'range':
        evidence['end'] = 99
    elif defect == 'equal':
        evidence['start'] = evidence['end']
    elif defect == 'quote':
        evidence['quote'] = 'Wrong Name'
    else:
        evidence['pointer'] = '/products/1/name'
        evidence['start'] = 0
        evidence['end'] = 16
        evidence['quote'] = 'Zeolite Capsules'
    paths = build_package(tmp_path, facts=facts)

    assert (await failed_code(loader, paths)).code == 'invalid_evidence'


@pytest.mark.parametrize(
    'defect',
    [
        'price-comma',
        'quantity-zero',
        'text-unit',
        'price-derivation',
        'edge-missing',
        'edge-extra',
        'edge-duplicate',
        'support-contradiction',
    ],
)
async def test_inconsistent_facts_fail(
    loader: ModuleType, tmp_path: Path, defect: str
) -> None:
    facts = facts_payload()
    powder = facts['products'][0]
    price = next(item for item in powder['facts'] if item['predicate'] == 'price')
    quantity = next(
        item for item in powder['facts'] if item['predicate'] == 'package_quantity'
    )
    form = next(item for item in powder['facts'] if item['predicate'] == 'form')
    support = next(
        item for item in powder['predicate_support'] if item['predicate'] == 'goes_with'
    )
    first_edge = powder['facts'][7]
    if defect == 'price-comma':
        price['value'] = '18,00'
    elif defect == 'quantity-zero':
        quantity['value'] = '050'
    elif defect == 'text-unit':
        form['unit'] = 'g'
    elif defect == 'price-derivation':
        price['derivation'] = 'literal'
    elif defect == 'edge-missing':
        powder['facts'] = [
            item
            for item in powder['facts']
            if item['id'] != 'zeolite-powder-200:goes_with:1'
        ]
    elif defect == 'edge-extra':
        extra = copy_case(first_edge)
        extra['id'] = 'zeolite-powder-200:goes_with:2'
        extra['value'] = 'travel-pill-box'
        powder['facts'].append(extra)
    elif defect == 'edge-duplicate':
        duplicate = copy_case(first_edge)
        duplicate['id'] = 'zeolite-powder-200:goes_with:2'
        powder['facts'].append(duplicate)
    else:
        support['status'] = 'absent'
    paths = build_package(tmp_path, facts=facts)

    assert (await failed_code(loader, paths)).code == 'inconsistent_fact'


# === Cross-field invariants ===


@pytest.mark.parametrize(
    ('defect', 'observation'),
    [
        (
            'missing-stage',
            {
                'outcome': 'answer',
                'stage': None,
                'answer': {
                    'customer_reply': 'Hi',
                    'upsell_hint': '',
                    'upsell_product_id': None,
                    'kb_match': 'none',
                },
                'error_code': None,
            },
        ),
        (
            'missing-answer',
            {
                'outcome': 'answer',
                'stage': 'model_output',
                'answer': None,
                'error_code': None,
            },
        ),
        (
            'failure-with-stage',
            {
                'outcome': 'provider_error',
                'stage': 'model_output',
                'answer': None,
                'error_code': 'timeout',
            },
        ),
        (
            'failure-with-answer',
            {
                'outcome': 'provider_error',
                'stage': None,
                'answer': {
                    'customer_reply': 'Hi',
                    'upsell_hint': '',
                    'upsell_product_id': None,
                    'kb_match': 'none',
                },
                'error_code': 'timeout',
            },
        ),
        (
            'failure-without-code',
            {
                'outcome': 'provider_error',
                'stage': None,
                'answer': None,
                'error_code': None,
            },
        ),
        (
            'failure-foreign-code',
            {
                'outcome': 'provider_error',
                'stage': None,
                'answer': None,
                'error_code': 'weird',
            },
        ),
        (
            'answer-with-code',
            {
                'outcome': 'answer',
                'stage': 'model_output',
                'answer': {
                    'customer_reply': 'Hi',
                    'upsell_hint': '',
                    'upsell_product_id': None,
                    'kb_match': 'none',
                },
                'error_code': 'timeout',
            },
        ),
    ],
    ids=[
        'missing-stage',
        'missing-answer',
        'failure-with-stage',
        'failure-with-answer',
        'failure-without-code',
        'failure-foreign-code',
        'answer-with-code',
    ],
)
async def test_observation_matrix_fails(
    loader: ModuleType, tmp_path: Path, defect: str, observation: dict[str, Any]
) -> None:
    corpus = corpus_payload()
    case_of(corpus)['observation'] = observation
    paths = build_package(tmp_path, corpora=[corpus])

    assert (await failed_code(loader, paths)).code == 'invalid_observation'


@pytest.mark.parametrize(
    ('defect', 'changes'),
    [
        ('pending-verdict', {'verdict': 'correct'}),
        ('pending-reviewer', {'reviewed_by': 'someone'}),
        (
            'confirmed-incomplete',
            {
                'status': 'confirmed',
                'verdict': 'correct',
                'confirmation_ref': None,
                'reviewed_by': 'ref',
                'reviewed_at': '2026-10-01T12:00:00Z',
            },
        ),
        (
            'disputed-verdict',
            {
                'status': 'disputed',
                'verdict': 'incorrect',
                'reviewed_by': 'ref',
                'reviewed_at': '2026-10-01T12:00:00Z',
                'confirmation_ref': 'x',
            },
        ),
        (
            'non-utc-time',
            {
                'status': 'confirmed',
                'verdict': 'correct',
                'reviewed_by': 'ref',
                'reviewed_at': '2026-10-01T12:00:00+00:00',
                'confirmation_ref': 'x',
            },
        ),
        (
            'empty-rationale',
            {
                'status': 'confirmed',
                'verdict': 'correct',
                'rationale': '',
                'reviewed_by': 'ref',
                'reviewed_at': '2026-10-01T12:00:00Z',
                'confirmation_ref': 'x',
            },
        ),
    ],
    ids=[
        'pending-verdict',
        'pending-reviewer',
        'confirmed-incomplete',
        'disputed-verdict',
        'non-utc-time',
        'empty-rationale',
    ],
)
async def test_label_matrix_fails(
    loader: ModuleType, tmp_path: Path, defect: str, changes: dict[str, Any]
) -> None:
    corpus = corpus_payload()
    case_of(corpus)['label'].update(changes)
    paths = build_package(tmp_path, corpora=[corpus])

    assert (await failed_code(loader, paths)).code == 'invalid_label'


@pytest.mark.parametrize(
    ('defect', 'origin'),
    [
        (
            'recorded-no-reference',
            {
                'kind': 'recorded',
                'reference': None,
                'sha256': None,
                'parent_case_id': None,
                'record_pointer': '',
                'generation': None,
            },
        ),
        (
            'recorded-with-parent',
            {
                'kind': 'recorded',
                'reference': 'runs/r1.json',
                'sha256': ZERO,
                'parent_case_id': 'example-case-price',
                'record_pointer': '',
                'generation': {
                    'provider': None,
                    'model': None,
                    'max_output_tokens': 1,
                    'temperature': None,
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'attempts': 1,
                    'run_reference': None,
                },
            },
        ),
        (
            'recorded-no-generation',
            {
                'kind': 'recorded',
                'reference': 'runs/r1.json',
                'sha256': ZERO,
                'parent_case_id': None,
                'record_pointer': '',
                'generation': None,
            },
        ),
        (
            'authored-with-generation',
            {
                'kind': 'agent_authored',
                'reference': None,
                'sha256': None,
                'parent_case_id': None,
                'record_pointer': None,
                'generation': {
                    'provider': None,
                    'model': None,
                    'max_output_tokens': 1,
                    'temperature': None,
                    'input_tokens': 0,
                    'output_tokens': 0,
                    'attempts': 1,
                    'run_reference': None,
                },
            },
        ),
        (
            'authored-half-reference',
            {
                'kind': 'agent_authored',
                'reference': 'only-reference.json',
                'sha256': None,
                'parent_case_id': None,
                'record_pointer': None,
                'generation': None,
            },
        ),
        (
            'derived-with-pointer',
            derived_origin('example-case-price') | {'record_pointer': ''},
        ),
    ],
    ids=[
        'recorded-no-reference',
        'recorded-with-parent',
        'recorded-no-generation',
        'authored-with-generation',
        'authored-half-reference',
        'derived-with-pointer',
    ],
)
async def test_origin_matrix_fails(
    loader: ModuleType, tmp_path: Path, defect: str, origin: dict[str, Any]
) -> None:
    corpus = corpus_payload()
    if defect == 'derived-with-pointer':
        second = copy_case(case_of(corpus))
        second['id'] = 'case-b'
        corpus['cases'].append(second)
        case_of(corpus)['answer_origin'] = {**origin, 'parent_case_id': 'case-b'}
    else:
        case_of(corpus)['answer_origin'] = origin
    paths = build_package(tmp_path, corpora=[corpus])

    assert (await failed_code(loader, paths)).code == 'invalid_label'


# === Partitions ===


async def test_group_across_partitions_fails(
    loader: ModuleType, tmp_path: Path
) -> None:
    first = corpus_payload()
    first['partition'] = 'development'
    second = corpus_payload()
    second['partition'] = 'holdout'
    case_of(second)['id'] = 'case-b'
    paths = build_package(tmp_path, corpora=[first, second])

    assert (await failed_code(loader, paths)).code == 'split_leakage'


async def test_duplicate_case_across_corpora_fails(
    loader: ModuleType, tmp_path: Path
) -> None:
    first = corpus_payload()
    first['partition'] = 'development'
    second = corpus_payload()
    second['partition'] = 'holdout'
    paths = build_package(tmp_path, corpora=[first, second])

    assert (await failed_code(loader, paths)).code == 'duplicate_id'


# === Isolation ===


async def test_metadata_changes_keep_projection_equal(
    loader: ModuleType, tmp_path: Path
) -> None:
    first = corpus_payload()
    first['partition'] = 'development'
    second = corpus_payload()
    second['partition'] = 'holdout'
    second_case = case_of(second)
    second_case['id'] = 'case-b'
    second_case['group_id'] = 'group-b'
    second_case['categories'] = ['completeness_hint']
    second_case['question_origin']['kind'] = 'human_authored'
    second_case['label']['rationale'] = 'Other wording'
    second_case['label']['proposed_verdict'] = None
    paths = build_package(tmp_path, corpora=[first, second])
    package = await loader.load_quality_package(tmp_path, *paths[:3], list(paths[3]))
    left = package.cases[0].assessment
    right = package.cases[1].assessment

    assert left.question.model_dump(mode='json') == right.question.model_dump(
        mode='json'
    )
    assert left.observation.model_dump(mode='json') == right.observation.model_dump(
        mode='json'
    )
    assert [item.model_dump(mode='json') for item in left.product_facts] == [
        item.model_dump(mode='json') for item in right.product_facts
    ]
    assert left.catalogue.company == right.catalogue.company
    assert [product.id for product in left.catalogue.products] == [
        product.id for product in right.catalogue.products
    ]


# === File boundary ===


async def test_document_reads_run_once_outside_event_loop(
    loader: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = build_package(tmp_path)
    loop_thread = threading.get_ident()
    original = loader.read_quality_bytes
    reads: list[bool] = []

    def observe_read(path: Path) -> bytes:
        """Observe actual file reads."""
        reads.append(threading.get_ident() != loop_thread)
        result = original(path)
        assert isinstance(result, bytes)
        return result

    monkeypatch.setattr(loader, 'read_quality_bytes', observe_read)
    package = await loader.load_quality_package(tmp_path, *paths[:3], list(paths[3]))

    assert package.cases[0].case.id == 'example-case-price'
    assert reads == [True, True, True, True, True, True]

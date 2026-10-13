"""Extended evaluation contract tests."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from reply_assistant.quality_corpus import QualityInputError, load_quality_package

# === Public fixtures ===

ROOT = Path(__file__).parents[1]
DATA = ROOT / 'evals/quality/v1'


def command_module() -> ModuleType:
    """Load the quality command."""
    spec = importlib.util.spec_from_file_location(
        'quality_extension_command', ROOT / 'scripts/evaluate_quality.py'
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pinned_json(value: Any) -> str:
    """Hash canonical question bytes."""
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(',', ':')
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def extended_package(
    folder: Path,
    *,
    recommendation: str | None = 'zeolite-capsules-90',
    hint: str = 'Offer Zeolite Capsules.',
    identifier: str | None = 'zeolite-capsules-90',
    unknown: bool = False,
    failure: bool = False,
    price: str = '18.00',
    extended: bool = True,
) -> Path:
    """Write a public fixture."""
    folder.mkdir()
    for name in ('sources.json', 'facts.json'):
        (folder / name).write_bytes((DATA / name).read_bytes())
    questions = json.loads((DATA / 'examples/questions.json').read_bytes())
    question = questions['questions'][0]
    if extended:
        questions['document_kind'] = 'quality_questions_v2'
        questions['schema_version'] = 2
        question['message'] = (
            'What is the price of Zeolite Powder? '
            'Recommend Zeolite Capsules to the manager.'
        )
        question['required_recommendations'] = (
            [{'field': 'upsell_hint', 'product_id': recommendation}]
            if recommendation is not None
            else []
        )
        question['required_unknown_information'] = (
            [
                {
                    'field': 'customer_reply',
                    'product_id': 'zeolite-powder-200',
                    'property': 'production date',
                }
            ]
            if unknown
            else []
        )
        if unknown:
            question['message'] += ' What is its production date?'
            question['allowed_kb_matches'] = ['partial']
            question['basis'] = (
                'The price is present, but the catalogue does not give a production '
                'date. The question has partial source coverage.'
            )
    questions_path = folder / 'questions.json'
    questions_path.write_text(json.dumps(questions), encoding='utf-8')
    corpus = json.loads((DATA / 'examples/corpus-valid.json').read_bytes())
    corpus['questions_sha256'] = hashlib.sha256(questions_path.read_bytes()).hexdigest()
    case = corpus['cases'][0]
    case['question_sha256'] = pinned_json(question)
    case['observation']['answer'] = {
        'customer_reply': f'Zeolite Powder costs {price} USD.',
        'upsell_hint': hint,
        'upsell_product_id': identifier,
        'kb_match': 'partial' if unknown else 'found',
    }
    if failure:
        case['observation'] = {
            'outcome': 'provider_error',
            'stage': None,
            'answer': None,
            'error_code': 'timeout',
        }
    package = folder / 'corpus.json'
    package.write_text(json.dumps(corpus), encoding='utf-8')
    return package


def replay(package: Path, output: Path) -> tuple[int, dict[str, Any], str]:
    """Run and read reports."""
    code = command_module().main(
        ['replay', '--package', str(package), '--out', str(output)]
    )
    assert (output / 'report.json').is_file()
    return (
        code,
        json.loads((output / 'report.json').read_bytes()),
        (output / 'report.md').read_text(encoding='utf-8'),
    )


async def load_extended(package: Path) -> Any:
    """Load the complete package."""
    return await load_quality_package(
        ROOT,
        package.parent / 'sources.json',
        package.parent / 'facts.json',
        package.parent / 'questions.json',
        [package],
    )


def rebind_questions(package: Path, questions: dict[str, Any]) -> None:
    """Write renewed question bindings."""
    document = package.parent / 'questions.json'
    document.write_text(json.dumps(questions), encoding='utf-8')
    corpus = json.loads(package.read_bytes())
    corpus['questions_sha256'] = hashlib.sha256(document.read_bytes()).hexdigest()
    corpus['cases'][0]['question_sha256'] = pinned_json(questions['questions'][0])
    package.write_text(json.dumps(corpus), encoding='utf-8')


# === Obligation behavior ===


def test_requested_product_overrides_consistent_wrong_recommendation(
    tmp_path: Path,
) -> None:
    package = extended_package(
        tmp_path / 'package',
        hint='Offer Measuring Spoon.',
        identifier='measuring-spoon',
    )

    code, report, _ = replay(package, tmp_path / 'result')

    assert code == 1
    assert report['cases'][0]['factual_verdict'] == 'error'
    assert report['cases'][0]['grounds'] == [
        'recommendation_mismatch: expected zeolite-capsules-90, found measuring-spoon'
    ]


def test_missing_directive_fails_despite_requested_product_price(
    tmp_path: Path,
) -> None:
    package = extended_package(
        tmp_path / 'package', hint='Zeolite Capsules costs 24.00 USD.'
    )

    code, report, _ = replay(package, tmp_path / 'result')

    assert code == 1
    assert report['cases'][0]['factual_verdict'] == 'error'
    assert report['cases'][0]['grounds'] == ['incompleteness']


def test_unknown_recommendation_wording_is_not_proven_omission(
    tmp_path: Path,
) -> None:
    package = extended_package(
        tmp_path / 'package', hint='A suitable suggestion is Zeolite Capsules.'
    )

    code, report, _ = replay(package, tmp_path / 'result')

    assert code == 1
    assert report['cases'][0]['factual_verdict'] == 'manual_review'
    assert (
        'unresolved_recommendation: zeolite-capsules-90'
        in report['cases'][0]['unresolved']
    )


def test_unknown_information_cannot_be_confirmed_by_price_and_directive(
    tmp_path: Path,
) -> None:
    package = extended_package(tmp_path / 'package', unknown=True)

    code, report, _ = replay(package, tmp_path / 'result')

    assert code == 1
    assert report['cases'][0]['factual_verdict'] == 'manual_review'
    assert report['cases'][0]['unresolved'] == [
        'unresolved_unknown_information: customer_reply: production date '
        'of zeolite-powder-200'
    ]


def test_proven_error_keeps_priority_over_unknown_information(
    tmp_path: Path,
) -> None:
    package = extended_package(tmp_path / 'package', unknown=True, price='99.00')

    code, report, _ = replay(package, tmp_path / 'result')

    assert code == 1
    assert report['cases'][0]['factual_verdict'] == 'error'
    assert report['cases'][0]['grounds'] == [
        'price_mismatch: expected 18.00 USD, found 99.00 USD'
    ]
    assert report['cases'][0]['unresolved'] == [
        'unresolved_unknown_information: customer_reply: production date '
        'of zeolite-powder-200'
    ]


@pytest.mark.asyncio
async def test_recommendation_target_is_verified_in_selected_source(
    tmp_path: Path,
) -> None:
    package = extended_package(tmp_path / 'package', recommendation='hand-grinder')

    with pytest.raises(QualityInputError) as error:
        await load_extended(package)

    assert error.value.code == 'unknown_reference'
    assert error.value.location == 'questions.0.required_recommendations.0.product_id'


@pytest.mark.asyncio
async def test_unknown_information_subject_is_verified_before_assessment(
    tmp_path: Path,
) -> None:
    package = extended_package(tmp_path / 'package', unknown=True)
    questions_path = package.parent / 'questions.json'
    questions = json.loads(questions_path.read_bytes())
    questions['questions'][0]['required_unknown_information'][0]['product_id'] = (
        'hand-grinder'
    )
    rebind_questions(package, questions)

    with pytest.raises(QualityInputError) as error:
        await load_extended(package)

    assert error.value.code == 'unknown_reference'
    assert error.value.location == (
        'questions.0.required_unknown_information.0.product_id'
    )


# === Complete report behavior ===


@pytest.mark.asyncio
async def test_duplicate_unknown_information_is_rejected_as_duplicate_obligation(
    tmp_path: Path,
) -> None:
    package = extended_package(tmp_path / 'package', unknown=True)
    questions_path = package.parent / 'questions.json'
    questions = json.loads(questions_path.read_bytes())
    obligations = questions['questions'][0]['required_unknown_information']
    obligations.append(dict(obligations[0]))
    rebind_questions(package, questions)

    with pytest.raises(QualityInputError) as error:
        await load_extended(package)

    assert error.value.code == 'duplicate_id'
    assert error.value.location == 'questions.0.required_unknown_information.1'


def test_cli_reports_complete_observation_provenance_and_claim_fields(
    tmp_path: Path,
) -> None:
    package = extended_package(tmp_path / 'package', extended=False)

    code, report, markdown = replay(package, tmp_path / 'result')
    case = report['cases'][0]

    assert code == 0
    assert report['schema_version'] == 2
    assert case['context']['observation'] == {
        'outcome': 'answer',
        'stage': 'model_output',
        'answer': {
            'customer_reply': 'Zeolite Powder costs 18.00 USD.',
            'upsell_hint': 'Offer Zeolite Capsules.',
            'upsell_product_id': 'zeolite-capsules-90',
            'kb_match': 'found',
        },
        'error_code': None,
    }
    assert case['context']['question']['required_claims'][0]['predicate'] == 'price'
    assert case['context']['question_origin']['kind'] == 'agent_authored'
    assert case['context']['label']['status'] == 'pending'
    assert [(claim['kind'], claim['field']) for claim in case['claims']] == [
        ('price', 'customer_reply'),
        ('directive', 'upsell_hint'),
    ]
    assert 'Upsell hint: Offer Zeolite Capsules.' in markdown
    assert 'Upsell product ID: zeolite-capsules-90' in markdown
    assert 'KB match: found' in markdown
    assert 'Stage: model_output' in markdown
    assert 'upsell_hint: directive' in markdown


@pytest.mark.parametrize(
    ('extended', 'expected_version', 'expected_hash'),
    [
        (
            False,
            1,
            '71c90d118b173df5e002e5e1978022213d0d3258c08bdc4076c11057ce28d3bb',
        ),
        (
            True,
            2,
            '16892038fb56cc2f375d46fc1869c41d45d7f167562e22c53012adf98292af79',
        ),
    ],
)
def test_cli_markdown_keeps_question_binding_context(
    tmp_path: Path,
    extended: bool,
    expected_version: int,
    expected_hash: str,
) -> None:
    package = extended_package(tmp_path / 'package', extended=extended)

    code, report, markdown = replay(package, tmp_path / 'result')
    context = report['cases'][0]['context']

    assert code == 0
    assert context['group_id'] == 'example-group-price'
    assert context['question_sha256'] == expected_hash
    assert context['question_schema_version'] == expected_version
    assert 'Group ID: example-group-price' in markdown
    assert f'Question SHA256: {expected_hash}' in markdown
    assert f'Question schema version: {expected_version}' in markdown


def test_report_preserves_field_and_text_of_unchecked_content(
    tmp_path: Path,
) -> None:
    package = extended_package(
        tmp_path / 'package',
        hint='Unknown manager wording.',
        recommendation=None,
        extended=False,
    )

    code, report, markdown = replay(package, tmp_path / 'result')

    assert code == 1
    assert report['cases'][0]['coverage'][1]['unchecked'] == [
        {'start': 0, 'end': 23, 'text': 'Unknown manager wording'}
    ]
    assert report['cases'][0]['coverage'][1]['field'] == 'upsell_hint'
    assert 'upsell_hint: span 0-23: Unknown manager wording' in markdown


def test_recorded_failure_report_keeps_original_code_and_null_answer(
    tmp_path: Path,
) -> None:
    package = extended_package(tmp_path / 'package', failure=True, extended=False)

    code, report, markdown = replay(package, tmp_path / 'result')

    assert code == 2
    assert report['cases'][0]['context']['observation'] == {
        'outcome': 'provider_error',
        'stage': None,
        'answer': None,
        'error_code': 'timeout',
    }
    assert report['cases'][0]['coverage'] is None
    assert 'Observation: provider_error' in markdown
    assert 'Recorded error: timeout' in markdown


def test_evaluator_error_report_preserves_the_received_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    package = extended_package(tmp_path / 'package', extended=False)
    cli = command_module()

    def broken(*arguments: object) -> None:
        """Reject synthetic index construction."""
        raise RuntimeError('synthetic index failure')

    monkeypatch.setattr(cli, '_index_for', broken)
    output = tmp_path / 'out'

    code = cli.main(['replay', '--package', str(package), '--out', str(output)])
    case = json.loads((output / 'report.json').read_bytes())['cases'][0]

    assert code == 2
    assert case['execution_status'] == 'evaluator_error'
    assert case['factual_verdict'] is None
    assert case['answer'] == 'Zeolite Powder costs 18.00 USD.'
    assert case['context']['observation']['answer']['upsell_hint'] == (
        'Offer Zeolite Capsules.'
    )
    assert case['coverage'] is None

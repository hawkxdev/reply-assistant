"""Acceptance for issue 79."""

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

# === Data ===

ROOT = Path(__file__).parents[2]
DATA = ROOT / 'evals' / 'quality' / 'v1'
KB = ROOT / 'kb'
DISCLAIMER = 'This product is a food supplement and is not a medicine.'


# === Fixtures and helpers ===


@pytest.fixture
def rules() -> ModuleType:
    """Import the rules module."""
    return importlib.import_module('reply_assistant.quality_rules')


def catalogue(name: str) -> Any:
    """Parse one public catalogue."""
    data = yaml.safe_load((KB / name).read_text(encoding='utf-8'))
    module = __import__('reply_assistant.knowledge_base', fromlist=['_document'])
    return module._document(data)


def product_facts(source_id: str) -> list[Any]:
    """Collect the annotations of one source."""
    from reply_assistant.quality_corpus import load_quality_document
    from reply_assistant.quality_schema import Facts

    raw = asyncio_run(load_quality_document(DATA / 'facts.json'))
    document = raw.document
    assert isinstance(document, Facts)
    return [item for item in document.products if item.source_id == source_id]


def asyncio_run(awaitable: Any) -> Any:
    """Run one awaitable."""
    import asyncio

    return asyncio.run(awaitable)


def index_for(source_id: str) -> Any:
    """Build the fact index of one source."""
    facts = importlib.import_module('reply_assistant.quality_facts')
    source = 'public-en' if source_id == 'en' else 'public-ru'
    name = 'example-en.yaml' if source_id == 'en' else 'example-ru.yaml'
    return facts.build_fact_index(catalogue(name), product_facts(source))


def policy(stage: str | None = None, language: str = 'en') -> Any:
    """Build one source policy."""
    return importlib.import_module('reply_assistant.quality_rules').SourcePolicy(
        disclaimer=DISCLAIMER, stage=stage, language=language
    )


@pytest.fixture
def english_index() -> Any:
    """Build the English index."""
    return index_for('en')


def development_cases(rules: ModuleType) -> list[Any]:
    """Load the confirmed development package."""
    package = asyncio_run(
        importlib.import_module('reply_assistant.quality_corpus').load_quality_package(
            ROOT,
            DATA / 'sources.json',
            DATA / 'facts.json',
            DATA / 'questions.json',
            [DATA / 'development.json'],
        )
    )
    return list(package.cases)


def assess_case(rules: ModuleType, case: Any, stage: str | None = None) -> Any:
    """Aggregate one case through the grammar and aggregation."""
    assessment = case.assessment
    answer = assessment.observation.answer
    language = assessment.question.language
    index = index_for(language)
    customer = rules.assess_field(
        answer.customer_reply,
        index,
        'customer_reply',
        answer.upsell_product_id,
        policy(stage, language),
    )
    hint = rules.assess_field(
        answer.upsell_hint,
        index,
        'upsell_hint',
        answer.upsell_product_id,
        policy(stage, language),
    )
    return rules.assess_answer(
        customer, hint, assessment.question, answer, index, policy(stage, language)
    )


# === Corpus oracle ===


def test_every_confirmed_case_aggregates_confirmed(rules: ModuleType) -> None:
    cases = development_cases(rules)
    correct = [case for case in cases if case.case.label.verdict == 'correct']

    assert len(correct) == 20
    for case in correct:
        result = assess_case(rules, case)
        assert result.verdict == 'confirmed', (
            case.case.id,
            result.verdict,
            result.grounds,
            result.unresolved,
        )


def test_every_incorrect_case_aggregates_error(rules: ModuleType) -> None:
    cases = development_cases(rules)
    incorrect = [case for case in cases if case.case.label.verdict == 'incorrect']

    assert len(incorrect) == 20
    for case in incorrect:
        result = assess_case(rules, case)
        assert result.verdict == 'error', (
            case.case.id,
            result.verdict,
            result.grounds,
            result.unresolved,
        )


# === Metadata and aggregation ===


def test_metadata_errors_carry_metadata_grounds(rules: ModuleType) -> None:
    cases = development_cases(rules)
    kb_case = cases[0]
    kb_case.assessment.observation.answer.kb_match = 'none'
    kb_result = assess_case(rules, kb_case)

    upsell_case = next(
        case
        for case in cases
        if case.assessment.observation.answer.upsell_product_id is not None
    )
    upsell_case.assessment.observation.answer.upsell_product_id = 'ghost-product'
    upsell_result = assess_case(rules, upsell_case)

    assert kb_result.verdict == 'error'
    assert any('kb_match' in ground for ground in kb_result.grounds)
    assert upsell_result.verdict == 'error'
    assert any('upsell' in ground for ground in upsell_result.grounds)


def test_equal_repeats_and_mixed_prices(rules: ModuleType, english_index: Any) -> None:
    from reply_assistant.quality_schema import Answer

    cases = development_cases(rules)
    case = next(case for case in cases if case.case.id == 'case-price-en-1-correct')
    question = case.assessment.question

    def aggregate(answer: Answer) -> Any:
        """Aggregate one synthetic answer."""
        customer = rules.assess_field(
            answer.customer_reply, english_index, 'customer_reply', None, policy()
        )
        hint = rules.assess_field('', english_index, 'upsell_hint', None, policy())
        return rules.assess_answer(
            customer, hint, question, answer, english_index, policy()
        )

    equal = Answer(
        customer_reply=(
            'Zeolite Powder costs 18.00 USD. Zeolite Powder costs 18.00 USD.'
        ),
        upsell_hint='',
        upsell_product_id=None,
        kb_match='found',
    )
    mixed = Answer(
        customer_reply=(
            'Zeolite Powder costs 18.00 USD. Zeolite Powder costs 99.00 USD.'
        ),
        upsell_hint='',
        upsell_product_id=None,
        kb_match='found',
    )

    equal_result = aggregate(equal)
    mixed_result = aggregate(mixed)

    assert equal_result.verdict == 'confirmed'
    assert mixed_result.verdict == 'error'
    assert any('99.00' in ground for ground in mixed_result.grounds)


def test_unknown_tail_excludes_confirmed(rules: ModuleType, english_index: Any) -> None:
    from reply_assistant.quality_schema import Answer

    cases = development_cases(rules)
    case = next(case for case in cases if case.case.id == 'case-price-en-1-correct')
    question = case.assessment.question
    answer = Answer(
        customer_reply='Zeolite Powder costs 18.00 USD and ships tomorrow.',
        upsell_hint='',
        upsell_product_id=None,
        kb_match='found',
    )
    customer = rules.assess_field(
        answer.customer_reply, english_index, 'customer_reply', None, policy()
    )
    hint = rules.assess_field('', english_index, 'upsell_hint', None, policy())
    result = rules.assess_answer(
        customer, hint, question, answer, english_index, policy()
    )

    assert result.verdict == 'manual_review'
    assert result.unresolved


def test_model_output_needs_no_disclaimer_suffix(rules: ModuleType) -> None:
    cases = development_cases(rules)
    case = next(case for case in cases if case.case.id == 'case-price-en-1-correct')

    without = assess_case(rules, case, stage=None)
    assert without.verdict == 'confirmed'

    answer = case.assessment.observation.answer
    answer.customer_reply = answer.customer_reply + '\n\n' + DISCLAIMER
    final = assess_case(rules, case, stage='final_suggestion')
    assert final.verdict == 'confirmed'


def test_metadata_changes_keep_the_verdict(rules: ModuleType) -> None:
    cases = development_cases(rules)
    case = cases[0]
    before = assess_case(rules, case).verdict

    case.case.id = 'mutated-case'
    case.case.group_id = 'mutated-group'
    case.case.categories = ['completeness_hint']
    case.case.label.rationale = 'Mutated rationale.'
    case.case.label.proposed_verdict = 'incorrect'
    after = assess_case(rules, case).verdict

    assert before == 'confirmed'
    assert after == before

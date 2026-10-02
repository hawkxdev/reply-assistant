"""Finite grammar unit tests."""

import asyncio
import importlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from reply_assistant.quality_corpus import load_quality_document
from reply_assistant.quality_schema import Facts

ROOT = Path(__file__).parents[1]
FACTS_PATH = ROOT / 'evals' / 'quality' / 'v1' / 'facts.json'


def build_index(catalogue_name: str, source_id: str) -> Any:
    """Build one catalogue index."""
    knowledge = importlib.import_module('reply_assistant.knowledge_base')
    data = yaml.safe_load((ROOT / 'kb' / catalogue_name).read_text(encoding='utf-8'))
    catalogue = knowledge._document(data)
    raw = asyncio.run(load_quality_document(FACTS_PATH))
    document = raw.document
    assert isinstance(document, Facts)
    annotations = [item for item in document.products if item.source_id == source_id]
    facts = importlib.import_module('reply_assistant.quality_facts')
    return facts.build_fact_index(catalogue, annotations)


@pytest.fixture(scope='module')
def rules() -> Any:
    """Import the rules module."""
    return importlib.import_module('reply_assistant.quality_rules')


@pytest.fixture(scope='module')
def english_index() -> Any:
    """Build the English index."""
    return build_index('example-en.yaml', 'public-en')


@pytest.fixture(scope='module')
def russian_index() -> Any:
    """Build the Russian index."""
    return build_index('example-ru.yaml', 'public-ru')


def covered(text: str, assessment: Any) -> str:
    """Join remainder slices."""
    return ''.join(text[span[0] : span[1]] for span in assessment.remainders)


def test_grouped_price_confirms(rules: Any, russian_index: Any) -> None:
    result = rules.assess_field('Ручная кофемолка стоит 3 900 RUB.', russian_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.matches is True
    assert claim.expected == '3900 RUB'
    assert claim.found == '3900 RUB'
    assert result.remainders == ()


def test_word_apostrophe_is_not_a_quote(rules: Any, english_index: Any) -> None:
    text = "Zeolite Powder costs 18.00 USD for a buyer's kitchen."
    result = rules.assess_field(text, english_index)

    assert result.protected is False
    assert len(result.claims) == 1
    assert result.claims[0].matches is True


def test_unclosed_angle_quote_protects(rules: Any, english_index: Any) -> None:
    result = rules.assess_field('«Zeolite Powder costs 18.00 USD.', english_index)

    assert result.protected is True
    assert result.protection_reason == 'quote'
    assert result.claims == ()


def test_two_subjects_stay_unresolved(rules: Any, english_index: Any) -> None:
    text = 'Zeolite Powder costs 18.00 USD, Measuring Spoon costs 4.00 USD.'
    result = rules.assess_field(text, english_index)

    assert result.claims == ()
    joined = covered(text, result)
    assert 'Zeolite Powder' in joined
    assert 'Measuring Spoon' in joined


def test_wrong_currency_is_an_error(rules: Any, english_index: Any) -> None:
    result = rules.assess_field('Zeolite Powder costs 18.00 RUB.', english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.matches is False
    assert claim.expected == '18.00 USD'
    assert claim.found == '18.00 RUB'


def test_wrong_form_unit_is_an_error(rules: Any, english_index: Any) -> None:
    text = 'Zeolite Powder comes as a powder in a 200 ml jar.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'form'
    assert claim.matches is False
    assert claim.expected == 'powder, 200 g jar'
    assert claim.found == 'powder in a 200 ml jar'


def test_repeated_wrong_price_keeps_both_spans(rules: Any, english_index: Any) -> None:
    text = 'Zeolite Powder costs 18.00 USD. Zeolite Powder costs 20.00 USD.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 2
    first, second = result.claims
    assert first.matches is True
    assert (first.start, first.end) == (0, 30)
    assert second.matches is False
    assert (second.start, second.end) == (32, 62)
    assert second.found == '20.00 USD'


def test_mixed_number_separators_stay_a_remainder(
    rules: Any, english_index: Any
) -> None:
    text = 'Zeolite Powder costs 1,000.00 USD.'
    result = rules.assess_field(text, english_index)

    assert result.claims == ()
    assert '1,000.00' in covered(text, result)


def test_question_mark_protects_the_field(rules: Any, english_index: Any) -> None:
    text = 'Zeolite Powder costs 18.00 USD?'
    result = rules.assess_field(text, english_index)

    assert result.protected is True
    assert result.protection_reason == 'question'
    assert result.claims == ()


def test_curly_apostrophe_between_letters_is_not_a_quote(
    rules: Any, english_index: Any
) -> None:
    text = 'Zeolite Powder costs 18.00 USD for a buyer’s kitchen.'
    result = rules.assess_field(text, english_index)

    assert result.protected is False
    assert len(result.claims) == 1
    assert result.claims[0].matches is True


def test_mixed_space_kinds_stay_a_remainder(rules: Any, english_index: Any) -> None:
    text = 'Zeolite Powder costs 1 000 000 RUB.'
    result = rules.assess_field(text, english_index)

    assert result.claims == ()
    assert '1 000 000' in covered(text, result)


def test_non_positive_form_quantity_stays_a_remainder(
    rules: Any, english_index: Any
) -> None:
    zero = rules.assess_field(
        'Zeolite Powder comes as a powder in a 0 g jar.', english_index
    )
    fractional = rules.assess_field(
        'Zeolite Powder comes as a powder in a 0.5 g jar.', english_index
    )

    assert zero.claims == ()
    assert '0 g jar' in covered('Zeolite Powder comes as a powder in a 0 g jar.', zero)
    assert fractional.claims == ()
    assert '0.5 g jar' in covered(
        'Zeolite Powder comes as a powder in a 0.5 g jar.', fractional
    )


def test_f02_profile_confirms(rules: Any, english_index: Any) -> None:
    result = rules.assess_field(
        'Zeolite Capsules comes as capsules, 90 pieces.', english_index
    )

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'form'
    assert claim.matches is True
    assert claim.product_id == 'zeolite-capsules-90'
    assert claim.expected == 'capsules, 90 pieces'
    assert claim.found == 'capsules, 90 pieces'


def test_f03_profile_confirms(rules: Any, english_index: Any) -> None:
    result = rules.assess_field(
        'Mineral Clay Face Mask: paste in a 100 ml tube.', english_index
    )

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'form'
    assert claim.matches is True
    assert claim.expected == 'paste, 100 ml tube'
    assert claim.found == 'paste in a 100 ml tube'


def test_f05_profile_confirms(rules: Any, english_index: Any) -> None:
    result = rules.assess_field(
        'Travel Pill Box: plastic box, 7 sections.', english_index
    )

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'form'
    assert claim.matches is True
    assert claim.expected == 'plastic box, 7 sections'
    assert claim.found == 'plastic box, 7 sections'


def test_f06_alternative_spelling_confirms(rules: Any, russian_index: Any) -> None:
    result = rules.assess_field('Бразилия Сантос: зерно в пачке 250 г.', russian_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'form'
    assert claim.matches is True
    assert claim.expected == 'зерно, пачка 250 г'
    assert claim.found == 'зерно в пачке 250 г'


def test_f07_profile_confirms(rules: Any, russian_index: Any) -> None:
    result = rules.assess_field('Бумажные фильтры: упаковка 100 штук.', russian_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'form'
    assert claim.matches is True
    assert claim.product_id == 'paper-filters-100'
    assert claim.expected == 'упаковка 100 штук'
    assert claim.found == 'упаковка 100 штук'


def test_prefixed_price_construction_confirms(rules: Any, english_index: Any) -> None:
    text = 'The price of Zeolite Powder is 18.00 USD.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.matches is True
    assert claim.product_id == 'zeolite-powder-200'
    assert (claim.start, claim.end) == (0, 40)


def test_russian_prefixed_price_confirms(rules: Any, russian_index: Any) -> None:
    result = rules.assess_field('Цена Бразилия Сантос: 690 RUB.', russian_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.matches is True
    assert claim.product_id == 'brazil-santos-250'
    assert claim.found == '690 RUB'


def test_compound_colon_confirms_both_slots(rules: Any, russian_index: Any) -> None:
    result = rules.assess_field(
        'Бразилия Сантос: зерно, пачка 250 г, цена 690 RUB.', russian_index
    )

    kinds = sorted(claim.kind for claim in result.claims)
    assert kinds == ['form', 'price']
    assert all(claim.matches for claim in result.claims)
    assert all(claim.product_id == 'brazil-santos-250' for claim in result.claims)

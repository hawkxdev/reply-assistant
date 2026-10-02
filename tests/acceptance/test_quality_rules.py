"""Acceptance for issue 73."""

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

# === Data ===

ROOT = Path(__file__).parents[2]
KB = ROOT / 'kb'
FACTS = ROOT / 'evals' / 'quality' / 'v1' / 'facts.json'


# === Fixtures and helpers ===


@pytest.fixture
def rules() -> ModuleType:
    """Import the rules module."""
    return importlib.import_module('reply_assistant.quality_rules')


def catalogue(name: str) -> Any:
    """Parse one public catalogue."""
    data = yaml.safe_load((KB / name).read_text(encoding='utf-8'))
    module = importlib.import_module('reply_assistant.knowledge_base')
    return module._document(data)


def product_facts(source_id: str) -> list[Any]:
    """Collect the annotations of one source."""
    from reply_assistant.quality_corpus import load_quality_document
    from reply_assistant.quality_schema import Facts

    raw = asyncio_run(load_quality_document(FACTS))
    document = raw.document
    assert isinstance(document, Facts)
    return [item for item in document.products if item.source_id == source_id]


def asyncio_run(awaitable: Any) -> Any:
    """Run one awaitable."""
    import asyncio

    return asyncio.run(awaitable)


@pytest.fixture
def english_index() -> Any:
    """Build the English index."""
    facts = importlib.import_module('reply_assistant.quality_facts')
    return facts.build_fact_index(
        catalogue('example-en.yaml'), product_facts('public-en')
    )


@pytest.fixture
def russian_index() -> Any:
    """Build the Russian index."""
    facts = importlib.import_module('reply_assistant.quality_facts')
    return facts.build_fact_index(
        catalogue('example-ru.yaml'), product_facts('public-ru')
    )


def extract(text: str, span: tuple[int, int]) -> str:
    """Slice one span of the original text."""
    return text[span[0] : span[1]]


# === Confirmed constructions ===


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_price_confirms_with_original_span(
    rules: ModuleType, english_index: Any
) -> None:
    text = 'Zeolite Powder costs 18.00 USD.'
    result = rules.assess_field(text, english_index)

    assert result.protected is False
    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.product_id == 'zeolite-powder-200'
    assert claim.kind == 'price'
    assert claim.matches is True
    assert (claim.start, claim.end) == (0, 30)
    assert claim.expected == '18.00 USD'
    assert claim.found == '18.00 USD'
    assert result.remainders == ()


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_comma_decimal_confirms(rules: ModuleType, english_index: Any) -> None:
    text = 'Zeolite Powder costs 18,00 USD.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.matches is True
    assert claim.found == '18.00 USD'
    assert (claim.start, claim.end) == (0, 30)


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_wrong_price_is_an_error(rules: ModuleType, english_index: Any) -> None:
    text = 'Zeolite Powder costs 20.00 USD.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.matches is False
    assert claim.expected == '18.00 USD'
    assert claim.found == '20.00 USD'


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_russian_price_confirms_and_detects_error(
    rules: ModuleType, russian_index: Any
) -> None:
    good = rules.assess_field('Бразилия Сантос: цена 690 RUB.', russian_index)
    bad = rules.assess_field('Бразилия Сантос: цена 990 RUB.', russian_index)

    assert good.claims[0].matches is True
    assert good.claims[0].product_id == 'brazil-santos-250'
    assert bad.claims[0].matches is False
    assert bad.claims[0].found == '990 RUB'


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_compound_confirms_both_slots(rules: ModuleType, english_index: Any) -> None:
    text = 'Zeolite Powder comes as a powder in a 200 g jar and costs 18.00 USD.'
    result = rules.assess_field(text, english_index)

    kinds = sorted(claim.kind for claim in result.claims)
    assert kinds == ['form', 'price']
    assert all(claim.matches for claim in result.claims)
    assert all(claim.product_id == 'zeolite-powder-200' for claim in result.claims)


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_wrong_form_quantity_is_an_error(rules: ModuleType, english_index: Any) -> None:
    text = 'Zeolite Powder comes as a powder in a 500 g jar.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'form'
    assert claim.matches is False
    assert claim.expected == 'powder, 200 g jar'
    assert claim.found == 'powder in a 500 g jar'


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_spoon_form_profile_confirms_and_detects_error(
    rules: ModuleType, english_index: Any
) -> None:
    good = rules.assess_field('Measuring Spoon: steel spoon, 5 g.', english_index)
    bad = rules.assess_field('Measuring Spoon: steel spoon, 10 g.', english_index)

    assert good.claims[0].matches is True
    assert bad.claims[0].matches is False
    assert bad.claims[0].found == 'steel spoon, 10 g'


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_grinder_profile_confirms_and_detects_error(
    rules: ModuleType, russian_index: Any
) -> None:
    good = rules.assess_field(
        'Ручная кофемолка выпускается в форме стальные жернова, 30 г за раз.',
        russian_index,
    )
    bad = rules.assess_field(
        'Ручная кофемолка выпускается в форме стальные жернова, 60 г за раз.',
        russian_index,
    )

    assert good.claims[0].matches is True
    assert bad.claims[0].matches is False


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_foreign_subject_binds_own_value(rules: ModuleType, english_index: Any) -> None:
    text = 'Measuring Spoon costs 18.00 USD.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.product_id == 'measuring-spoon'
    assert claim.matches is False
    assert claim.expected == '4.00 USD'


# === Protected context and remainders ===


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_quoted_field_yields_no_claims(rules: ModuleType, english_index: Any) -> None:
    text = '"Zeolite Powder costs 18.00 USD."'
    result = rules.assess_field(text, english_index)

    assert result.protected is True
    assert result.protection_reason == 'quote'
    assert result.claims == ()


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_negation_protects_the_field(rules: ModuleType, english_index: Any) -> None:
    text = 'Zeolite Powder does not cost 18.00 USD.'
    result = rules.assess_field(text, english_index)

    assert result.protected is True
    assert result.protection_reason == 'negation'
    assert result.claims == ()


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_condition_marker_protects_the_field(
    rules: ModuleType, english_index: Any
) -> None:
    text = 'Zeolite Powder costs 18.00 USD\nif you order two jars.'
    result = rules.assess_field(text, english_index)

    assert result.protected is True
    assert result.protection_reason == 'condition'
    assert result.claims == ()


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_invalid_grouping_stays_a_remainder(
    rules: ModuleType, english_index: Any
) -> None:
    text = 'Zeolite Powder costs 3 9 00 RUB.'
    result = rules.assess_field(text, english_index)

    assert result.claims == ()
    assert len(result.remainders) >= 1
    covered = ''.join(extract(text, span) for span in result.remainders)
    assert '3 9 00' in covered


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_unknown_tail_stays_a_remainder(rules: ModuleType, english_index: Any) -> None:
    text = 'Zeolite Powder costs 18.00 USD and ships tomorrow.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    assert result.claims[0].matches is True
    covered = ''.join(extract(text, span) for span in result.remainders)
    assert 'ships tomorrow' in covered


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_second_sentence_reports_original_span(
    rules: ModuleType, english_index: Any
) -> None:
    text = 'Hello! Zeolite Powder costs 18.00 USD.'
    result = rules.assess_field(text, english_index)

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert (claim.start, claim.end) == (7, 37)
    assert extract(text, (claim.start, claim.end)) == 'Zeolite Powder costs 18.00 USD'


@pytest.mark.xfail(strict=True, reason='E07 not implemented')
def test_unknown_name_yields_no_claim(rules: ModuleType, english_index: Any) -> None:
    text = 'zeolite powder costs 18.00 USD.'
    result = rules.assess_field(text, english_index)

    assert result.protected is False
    assert result.claims == ()
    covered = ''.join(extract(text, span) for span in result.remainders)
    assert 'zeolite powder costs' in covered

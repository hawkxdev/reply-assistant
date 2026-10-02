"""Acceptance for issue 76."""

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
DISCLAIMER = 'This product is a food supplement and is not a medicine.'


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


def policy(language: str = 'en', stage: str | None = None) -> Any:
    """Build one source policy."""
    rules = importlib.import_module('reply_assistant.quality_rules')
    return rules.SourcePolicy(disclaimer=DISCLAIMER, stage=stage, language=language)


def extract(text: str, span: tuple[int, int]) -> str:
    """Slice one span of the original text."""
    return text[span[0] : span[1]]


# === Product constructions ===


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_description_confirms_and_foreign_text_stays_outside(
    rules: ModuleType, english_index: Any
) -> None:
    good = rules.assess_field(
        'Zeolite Powder: Finely milled natural zeolite for daily use with water.',
        english_index,
        'customer_reply',
    )
    foreign = rules.assess_field(
        'Zeolite Powder: A cosmetic clay mask for weekly skin care.',
        english_index,
        'customer_reply',
    )

    assert good.claims[0].kind == 'description'
    assert good.claims[0].matches is True
    assert foreign.claims == ()
    covered = ''.join(
        extract('Zeolite Powder: A cosmetic clay mask for weekly skin care.', span)
        for span in foreign.remainders
    )
    assert 'A cosmetic clay mask' in covered


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_batch_capacity_confirms_and_detects_error(
    rules: ModuleType, russian_index: Any
) -> None:
    good = rules.assess_field(
        'Ручная кофемолка перемалывает 30 г за раз.', russian_index, 'customer_reply'
    )
    bad = rules.assess_field(
        'Ручная кофемолка перемалывает 60 г за раз.', russian_index, 'customer_reply'
    )

    assert good.claims[0].kind == 'batch_capacity'
    assert good.claims[0].matches is True
    assert bad.claims[0].matches is False
    assert bad.claims[0].found == '60 г'


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_object_mass_stays_unresolved_or_errors(
    rules: ModuleType, english_index: Any, russian_index: Any
) -> None:
    spoon = rules.assess_field(
        'Measuring Spoon weighs 5 g.', english_index, 'customer_reply'
    )
    grinder = rules.assess_field(
        'Ручная кофемолка весит 30 г.', russian_index, 'customer_reply'
    )

    assert spoon.claims == ()
    covered = ''.join(
        extract('Measuring Spoon weighs 5 g.', span) for span in spoon.remainders
    )
    assert 'weighs 5 g' in covered
    assert grinder.claims[0].kind == 'object_mass'
    assert grinder.claims[0].matches is False


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_filter_size_keeps_the_code(rules: ModuleType, russian_index: Any) -> None:
    good = rules.assess_field(
        'Бумажные фильтры для воронки размера 02.', russian_index, 'customer_reply'
    )
    bad = rules.assess_field(
        'Бумажные фильтры для воронки размера 2.', russian_index, 'customer_reply'
    )

    assert good.claims[0].kind == 'filter_size'
    assert good.claims[0].matches is True
    assert bad.claims[0].matches is False
    assert bad.claims[0].found == '2'


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_relation_membership_is_directed(rules: ModuleType, english_index: Any) -> None:
    good = rules.assess_field(
        'Zeolite Powder pairs with Measuring Spoon.', english_index, 'customer_reply'
    )
    bad = rules.assess_field(
        'Measuring Spoon pairs with Zeolite Powder.', english_index, 'customer_reply'
    )

    assert good.claims[0].kind == 'relation'
    assert good.claims[0].matches is True
    assert bad.claims[0].matches is False


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_presence_statements_are_unsupported_errors(
    rules: ModuleType, english_index: Any, russian_index: Any
) -> None:
    stock = rules.assess_field(
        'Zeolite Powder is in stock.', english_index, 'customer_reply'
    )
    delivery = rules.assess_field(
        'We deliver to Atlantis.', english_index, 'customer_reply'
    )
    stock_ru = rules.assess_field(
        'Бразилия Сантос есть в наличии.', russian_index, 'customer_reply'
    )

    assert stock.claims[0].kind == 'stock'
    assert stock.claims[0].matches is False
    assert delivery.claims[0].kind == 'delivery'
    assert delivery.claims[0].matches is False
    assert stock_ru.claims[0].kind == 'stock'
    assert stock_ru.claims[0].matches is False


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_absence_templates_confirm_with_remainders(
    rules: ModuleType, english_index: Any, russian_index: Any
) -> None:
    delivery = rules.assess_field(
        'I do not have information about delivery to Atlantis or delivery times.',
        english_index,
        'customer_reply',
    )
    extended = rules.assess_field(
        'I do not have information about delivery to Atlantis or delivery times. '
        'We deliver tomorrow.',
        english_index,
        'customer_reply',
    )
    stock_ru = rules.assess_field(
        'В базе нет информации о наличии Бразилия Сантос.',
        russian_index,
        'customer_reply',
    )

    assert delivery.claims[0].kind == 'absence_delivery'
    assert delivery.claims[0].matches is True
    assert extended.claims[0].kind == 'absence_delivery'
    assert extended.claims[0].matches is True
    covered = ''.join(
        extract(
            'I do not have information about delivery to Atlantis or delivery '
            'times. We deliver tomorrow.',
            span,
        )
        for span in extended.remainders
    )
    assert 'We deliver tomorrow' in covered
    assert stock_ru.claims[0].kind == 'absence_stock'
    assert stock_ru.claims[0].matches is True


# === Hint, service phrases and disclaimer ===


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_directive_binds_the_recorded_upsell(
    rules: ModuleType, english_index: Any
) -> None:
    good = rules.assess_field(
        'Offer Measuring Spoon.', english_index, 'upsell_hint', 'measuring-spoon'
    )
    bad = rules.assess_field(
        'Offer Measuring Spoon.', english_index, 'upsell_hint', 'travel-pill-box'
    )
    free = rules.assess_field('Call us now!', english_index, 'upsell_hint', None)
    reply_directive = rules.assess_field(
        'Offer Measuring Spoon.', english_index, 'customer_reply', 'measuring-spoon'
    )

    assert good.claims[0].kind == 'directive'
    assert good.claims[0].matches is True
    assert bad.claims[0].matches is False
    assert free.claims == ()
    assert len(free.remainders) == 1
    assert reply_directive.claims == ()


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_service_phrases_follow_field_and_catalogue(
    rules: ModuleType, english_index: Any, russian_index: Any
) -> None:
    greeting = rules.assess_field(
        'Hello!', english_index, 'customer_reply', source_policy=policy()
    )
    doctor = rules.assess_field(
        'Please ask a doctor about health questions.',
        english_index,
        'customer_reply',
        source_policy=policy(),
    )
    doctor_ru = rules.assess_field(
        'Please ask a doctor about health questions.',
        russian_index,
        'customer_reply',
        source_policy=policy('ru'),
    )
    handoff_hint = rules.assess_field(
        'I can pass the question to a manager.', english_index, 'upsell_hint'
    )

    assert greeting.claims[0].kind == 'service'
    assert greeting.claims[0].matches is True
    assert doctor.claims[0].matches is True
    assert doctor_ru.claims == ()
    assert handoff_hint.claims[0].matches is True


@pytest.mark.xfail(strict=True, reason='E08 not implemented')
def test_disclaimer_requires_suffix_on_final_suggestion(
    rules: ModuleType, english_index: Any
) -> None:
    final = rules.assess_field(
        'Zeolite Powder costs 18.00 USD.\n\n' + DISCLAIMER,
        english_index,
        'customer_reply',
        source_policy=policy(stage='final_suggestion'),
    )
    missing = rules.assess_field(
        'Zeolite Powder costs 18.00 USD.',
        english_index,
        'customer_reply',
        source_policy=policy(stage='final_suggestion'),
    )
    wrong = rules.assess_field(
        'Zeolite Powder costs 18.00 USD.\n' + DISCLAIMER,
        english_index,
        'customer_reply',
        source_policy=policy(stage='final_suggestion'),
    )
    output = rules.assess_field(
        'Zeolite Powder costs 18.00 USD.',
        english_index,
        'customer_reply',
        source_policy=policy(stage='model_output'),
    )

    final_disclaimer = [claim for claim in final.claims if claim.kind == 'disclaimer']
    assert len(final_disclaimer) == 1
    assert final_disclaimer[0].matches is True
    missing_disclaimer = [
        claim for claim in missing.claims if claim.kind == 'disclaimer'
    ]
    assert len(missing_disclaimer) == 1
    assert missing_disclaimer[0].matches is False
    wrong_disclaimer = [claim for claim in wrong.claims if claim.kind == 'disclaimer']
    assert len(wrong_disclaimer) == 1
    assert wrong_disclaimer[0].matches is False
    assert [claim for claim in output.claims if claim.kind == 'disclaimer'] == []

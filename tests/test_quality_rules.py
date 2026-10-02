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


def test_description_intro_and_first_letter_confirms(
    rules: Any, english_index: Any
) -> None:
    text = (
        'Description of Zeolite Powder: finely milled natural zeolite '
        'for daily use with water.'
    )
    result = rules.assess_field(text, english_index, 'customer_reply')

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'description'
    assert claim.matches is True
    assert claim.expected == 'Finely milled natural zeolite for daily use with water.'
    assert claim.found == 'finely milled natural zeolite for daily use with water'


def test_description_russian_intro_confirms(rules: Any, russian_index: Any) -> None:
    text = 'Описание Бразилия Сантос: Кофе средней обжарки с нотами ореха и шоколада.'
    result = rules.assess_field(text, russian_index, 'customer_reply')

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'description'
    assert claim.matches is True
    assert claim.product_id == 'brazil-santos-250'


def test_batch_capacity_english_spelling_confirms(
    rules: Any, russian_index: Any
) -> None:
    result = rules.assess_field(
        'Ручная кофемолка grinds 30 g per batch.', russian_index, 'customer_reply'
    )

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'batch_capacity'
    assert claim.matches is True


def test_batch_capacity_volume_unit_stays_a_remainder(
    rules: Any, russian_index: Any
) -> None:
    text = 'Ручная кофемолка перемалывает 30 мл за раз.'
    result = rules.assess_field(text, russian_index, 'customer_reply')

    assert result.claims == ()
    assert 'перемалывает 30 мл за раз' in covered(text, result)


def test_filter_size_foreign_subject_stays_a_remainder(
    rules: Any, russian_index: Any
) -> None:
    text = 'Бразилия Сантос для воронки размера 02.'
    result = rules.assess_field(text, russian_index, 'customer_reply')

    assert result.claims == ()
    assert 'размера 02' in covered(text, result)


def test_relation_russian_spelling_is_directed(rules: Any, russian_index: Any) -> None:
    good = rules.assess_field(
        'Бразилия Сантос сочетается с Ручная кофемолка.',
        russian_index,
        'customer_reply',
    )
    bad = rules.assess_field(
        'Ручная кофемолка сочетается с Бразилия Сантос.',
        russian_index,
        'customer_reply',
    )

    assert good.claims[0].kind == 'relation'
    assert good.claims[0].matches is True
    assert bad.claims[0].matches is False


def test_directive_consider_spelling_binds(rules: Any, english_index: Any) -> None:
    result = rules.assess_field(
        'Consider Measuring Spoon.', english_index, 'upsell_hint', 'measuring-spoon'
    )

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'directive'
    assert claim.matches is True
    assert claim.expected == 'measuring-spoon'


def test_delivery_russian_and_days_templates_error(
    rules: Any, russian_index: Any, english_index: Any
) -> None:
    russian = rules.assess_field(
        'У нас есть доставка в Атлантиду.', russian_index, 'customer_reply'
    )
    days = rules.assess_field(
        'Delivery to Atlantis takes 3 days.', english_index, 'customer_reply'
    )

    assert russian.claims[0].kind == 'delivery'
    assert russian.claims[0].matches is False
    assert days.claims[0].kind == 'delivery'
    assert days.claims[0].matches is False


def test_absence_delivery_russian_template_confirms(
    rules: Any, russian_index: Any
) -> None:
    text = 'В базе нет информации о доставке в Атлантиду и сроках.'
    result = rules.assess_field(text, russian_index, 'customer_reply')

    assert result.protected is False
    assert result.claims[0].kind == 'absence_delivery'
    assert result.claims[0].matches is True


def test_absence_stock_english_template_confirms(
    rules: Any, english_index: Any
) -> None:
    result = rules.assess_field(
        'I do not have stock information for Measuring Spoon.',
        english_index,
        'customer_reply',
    )

    assert result.claims[0].kind == 'absence_stock'
    assert result.claims[0].matches is True
    assert result.claims[0].product_id == 'measuring-spoon'


def test_greeting_stays_a_remainder_in_the_hint(rules: Any, english_index: Any) -> None:
    text = 'Hello!'
    result = rules.assess_field(text, english_index, 'upsell_hint')

    assert result.claims == ()
    assert covered(text, result) == 'Hello'


def test_russian_greeting_confirms_as_service(rules: Any, russian_index: Any) -> None:
    result = rules.assess_field(
        'Здравствуйте!',
        russian_index,
        'customer_reply',
        source_policy=rules.SourcePolicy(language='ru'),
    )

    assert len(result.claims) == 1
    claim = result.claims[0]
    assert claim.kind == 'service'
    assert claim.matches is True


def test_handoff_beside_absence_claim_stays_a_service_fragment(
    rules: Any, english_index: Any
) -> None:
    text = (
        'I do not have information about delivery to Atlantis or delivery '
        'times. I can pass the question to a manager.'
    )
    result = rules.assess_field(text, english_index, 'customer_reply')

    assert [claim.kind for claim in result.claims] == ['absence_delivery']
    assert len(result.service_fragments) == 1
    fragment = result.service_fragments[0]
    assert fragment.kind == 'service'
    assert text[fragment.start : fragment.end] == 'I can pass the question to a manager'
    assert result.remainders == ()


def test_greeting_beside_price_stays_a_service_fragment(
    rules: Any, english_index: Any
) -> None:
    text = 'Hello! Zeolite Powder costs 18.00 USD.'
    result = rules.assess_field(text, english_index, 'customer_reply')

    assert [claim.kind for claim in result.claims] == ['price']
    assert len(result.service_fragments) == 1
    fragment = result.service_fragments[0]
    assert fragment.kind == 'service'
    assert text[fragment.start : fragment.end] == 'Hello'
    assert result.remainders == ()


def test_model_output_carries_no_disclaimer_claim(
    rules: Any, english_index: Any
) -> None:
    text = (
        'Zeolite Powder costs 18.00 USD.\n\n'
        'This product is a food supplement and is not a medicine.'
    )
    result = rules.assess_field(
        text,
        english_index,
        'customer_reply',
        source_policy=rules.SourcePolicy(
            disclaimer='This product is a food supplement and is not a medicine.',
            stage='model_output',
        ),
    )

    assert [claim for claim in result.claims if claim.kind == 'disclaimer'] == []
    assert len(result.claims) == 1


def test_claims_and_remainders_cover_the_field(rules: Any, english_index: Any) -> None:
    text = (
        'Zeolite Powder costs 18.00 USD. I do not have stock information '
        'for Measuring Spoon.'
    )
    result = rules.assess_field(text, english_index, 'customer_reply')
    spans = [(claim.start, claim.end) for claim in result.claims]
    spans.extend(result.remainders)

    assert [claim.kind for claim in result.claims] == ['price', 'absence_stock']
    uncovered = [
        position
        for position in range(len(text))
        if not any(start <= position < end for start, end in spans)
        and text[position] not in '. '
    ]
    assert uncovered == []


def test_unknown_field_name_raises(rules: Any, english_index: Any) -> None:
    with pytest.raises(ValueError, match='unknown field'):
        rules.assess_field('Hello', english_index, 'summary')


def test_invalid_policy_values_raise(rules: Any, english_index: Any) -> None:
    with pytest.raises(ValueError, match='unknown stage'):
        rules.assess_field(
            'Hello!',
            english_index,
            'customer_reply',
            source_policy=rules.SourcePolicy(stage='replay'),
        )
    with pytest.raises(ValueError, match='unknown language'):
        rules.assess_field(
            'Hello!',
            english_index,
            'customer_reply',
            source_policy=rules.SourcePolicy(language='fr'),
        )


# === Answer aggregation ===

DISCLAIMER = 'This product is a food supplement and is not a medicine.'
FORBIDDEN_STEMS = (' cure', 'treats')
DELIVERY_REPLY = (
    'I do not have information about delivery to Atlantis or delivery '
    'times. I can pass the question to a manager.'
)


def required_claim(
    predicate: Any = 'price',
    product_id: Any = 'zeolite-powder-200',
    target_product_id: Any = None,
    stance: Any = 'affirmed',
) -> Any:
    """Build one required claim."""
    schema = importlib.import_module('reply_assistant.quality_schema')
    return schema.RequiredClaim(
        field='customer_reply',
        product_id=product_id,
        target_product_id=target_product_id,
        predicate=predicate,
        stance=stance,
    )


def required_action(kind: Any = 'handoff') -> Any:
    """Build one required action."""
    schema = importlib.import_module('reply_assistant.quality_schema')
    return schema.RequiredAction(field='customer_reply', kind=kind)


def make_question(
    claims: list[Any],
    actions: list[Any] | None = None,
    allowed: tuple[str, ...] = ('found',),
) -> Any:
    """Build one assessment question."""
    schema = importlib.import_module('reply_assistant.quality_schema')
    return schema.AssessmentQuestion(
        source_id='public-en',
        message='What does the catalogue say?',
        language='en',
        place=None,
        topic=None,
        required_claims=claims,
        required_actions=actions or [],
        allowed_kb_matches=list(allowed),
    )


def make_answer(
    reply: str,
    hint: str = '',
    upsell_product_id: Any = None,
    kb_match: Any = 'found',
) -> Any:
    """Build one recorded answer."""
    schema = importlib.import_module('reply_assistant.quality_schema')
    return schema.Answer(
        customer_reply=reply,
        upsell_hint=hint,
        upsell_product_id=upsell_product_id,
        kb_match=kb_match,
    )


def aggregate(rules: Any, index: Any, question: Any, answer: Any, policy: Any) -> Any:
    """Assess and aggregate one answer."""
    customer = rules.assess_field(
        answer.customer_reply, index, 'customer_reply', answer.upsell_product_id, policy
    )
    hint = rules.assess_field(
        answer.upsell_hint, index, 'upsell_hint', answer.upsell_product_id, policy
    )
    return rules.assess_answer(customer, hint, question, answer, index, policy)


def output_policy(rules: Any, language: str = 'en') -> Any:
    """Build one output stage policy."""
    return rules.SourcePolicy(stage='model_output', language=language)


def forbidden_policy(rules: Any) -> Any:
    """Build one stem checking policy."""
    return rules.SourcePolicy(
        stage='model_output', language='en', forbidden_stems=FORBIDDEN_STEMS
    )


def test_development_cases_aggregate_to_the_confirmed_labels() -> None:
    corpus = importlib.import_module('reply_assistant.quality_corpus')
    facts = importlib.import_module('reply_assistant.quality_facts')
    rules = importlib.import_module('reply_assistant.quality_rules')
    data = ROOT / 'evals' / 'quality' / 'v1'
    package = asyncio.run(
        corpus.load_quality_package(
            ROOT,
            data / 'sources.json',
            data / 'facts.json',
            data / 'questions.json',
            [data / 'development.json'],
        )
    )
    outcomes = []
    for item in package.cases:
        answer = item.assessment.observation.answer
        question = item.assessment.question
        index = facts.build_fact_index(
            item.assessment.catalogue, item.assessment.product_facts
        )
        policy = rules.SourcePolicy(stage='model_output', language=question.language)
        customer = rules.assess_field(
            answer.customer_reply,
            index,
            'customer_reply',
            answer.upsell_product_id,
            policy,
        )
        hint = rules.assess_field(
            answer.upsell_hint,
            index,
            'upsell_hint',
            answer.upsell_product_id,
            policy,
        )
        result = rules.assess_answer(customer, hint, question, answer, index, policy)
        outcomes.append((item.case.id, item.case.label.verdict, result.verdict))

    assert len(outcomes) == 40
    assert outcomes == [
        (case_id, label, 'confirmed' if label == 'correct' else 'error')
        for case_id, label, _verdict in outcomes
    ]


def test_kb_match_outside_the_allowed_set_is_a_metadata_error(
    rules: Any, english_index: Any
) -> None:
    question = make_question(
        [required_claim(predicate='delivery', product_id=None, stance='unknown')],
        [required_action('handoff')],
        allowed=('none',),
    )
    answer = make_answer(DELIVERY_REPLY, kb_match='found')

    result = aggregate(rules, english_index, question, answer, output_policy(rules))

    assert result.verdict == 'error'
    assert 'metadata_kb_match' in result.grounds


def test_unknown_upsell_identifier_is_a_metadata_error(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer(
        'Zeolite Powder costs 18.00 USD.', upsell_product_id='unknown-product'
    )

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        output_policy(rules),
    )

    assert result.verdict == 'error'
    assert 'metadata_upsell' in result.grounds


def test_equal_repeated_prices_confirm(rules: Any, english_index: Any) -> None:
    answer = make_answer(
        'Zeolite Powder costs 18.00 USD. Zeolite Powder costs 18.00 USD.'
    )

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        output_policy(rules),
    )

    assert result.verdict == 'confirmed'
    assert result.grounds == ()


def test_wrong_price_beside_correct_price_names_the_wrong_value(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer(
        'Zeolite Powder costs 18.00 USD. Zeolite Powder costs 20.00 USD.'
    )

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        output_policy(rules),
    )

    assert result.verdict == 'error'
    assert result.grounds == ('price_mismatch: expected 18.00 USD, found 20.00 USD',)


def test_unknown_tail_after_correct_claims_is_manual_review(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer('Zeolite Powder costs 18.00 USD and ships tomorrow.')

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        output_policy(rules),
    )

    assert result.verdict == 'manual_review'
    assert result.grounds == ()
    assert [reason for reason in result.unresolved if 'ships tomorrow' in reason]


def test_missing_price_with_remainder_routes_to_manual_review(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer('Zeolite Powder costs 1,000.00 USD.')

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        output_policy(rules),
    )

    assert result.verdict == 'manual_review'
    assert result.grounds == ()
    assert [
        reason
        for reason in result.unresolved
        if reason.startswith('unresolved_obligation: price')
    ]


def test_fully_parsed_reply_without_required_price_is_incomplete(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer('Hello!')

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        output_policy(rules),
    )

    assert result.verdict == 'error'
    assert 'incompleteness' in result.grounds


def test_missing_required_handoff_action_is_incomplete(
    rules: Any, english_index: Any
) -> None:
    question = make_question(
        [required_claim(predicate='delivery', product_id=None, stance='unknown')],
        [required_action('handoff')],
        allowed=('none',),
    )
    answer = make_answer(
        'I do not have information about delivery to Atlantis or delivery times.',
        kb_match='none',
    )

    result = aggregate(rules, english_index, question, answer, output_policy(rules))

    assert result.verdict == 'error'
    assert 'incompleteness' in result.grounds


def test_handoff_inside_a_claim_span_satisfies_the_action(
    rules: Any, english_index: Any
) -> None:
    question = make_question(
        [required_claim(predicate='delivery', product_id=None, stance='unknown')],
        [required_action('handoff')],
        allowed=('none',),
    )
    answer = make_answer(DELIVERY_REPLY, kb_match='none')
    absence = rules.Claim(
        product_id='',
        kind='absence_delivery',
        start=0,
        end=len(DELIVERY_REPLY),
        expected='no delivery information',
        found=DELIVERY_REPLY,
        matches=True,
    )
    customer = rules.FieldAssessment(
        protected=False,
        protection_reason=None,
        claims=(absence,),
        service_fragments=(),
        remainders=(),
    )
    empty = rules.FieldAssessment(
        protected=False,
        protection_reason=None,
        claims=(),
        service_fragments=(),
        remainders=(),
    )

    result = rules.assess_answer(
        customer, empty, question, answer, english_index, output_policy(rules)
    )

    assert result.verdict == 'confirmed'
    assert result.grounds == ()


def test_protected_reply_keeps_obligations_unresolved(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer('Zeolite Powder does not cost 18.00 USD.')

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        output_policy(rules),
    )

    assert result.verdict == 'manual_review'
    assert result.grounds == ()
    assert 'protected_context: customer_reply' in result.unresolved
    assert 'unresolved_obligation: price of zeolite-powder-200' in result.unresolved


def test_model_output_disclaimer_absence_confirms(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer('Zeolite Powder costs 18.00 USD.')
    question = make_question([required_claim()])
    output = aggregate(
        rules,
        english_index,
        question,
        answer,
        rules.SourcePolicy(stage='model_output', language='en', disclaimer=DISCLAIMER),
    )
    final = aggregate(
        rules,
        english_index,
        question,
        answer,
        rules.SourcePolicy(
            stage='final_suggestion', language='en', disclaimer=DISCLAIMER
        ),
    )

    assert output.verdict == 'confirmed'
    assert final.verdict == 'error'


def test_final_suggestion_disclaimer_confines_to_the_reply(
    rules: Any, english_index: Any
) -> None:
    policy = rules.SourcePolicy(
        stage='final_suggestion', language='en', disclaimer=DISCLAIMER
    )
    hint = rules.assess_field('', english_index, 'upsell_hint', None, policy)
    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        make_answer('Zeolite Powder costs 18.00 USD.\n\n' + DISCLAIMER),
        policy,
    )

    assert hint.claims == ()
    assert result.verdict == 'confirmed'
    assert result.grounds == ()


def test_kb_match_inside_the_allowed_set_keeps_the_verdict(
    rules: Any, english_index: Any
) -> None:
    question = make_question([required_claim()], allowed=('found', 'partial'))
    found = aggregate(
        rules,
        english_index,
        question,
        make_answer('Zeolite Powder costs 18.00 USD.', kb_match='found'),
        output_policy(rules),
    )
    partial = aggregate(
        rules,
        english_index,
        question,
        make_answer('Zeolite Powder costs 18.00 USD.', kb_match='partial'),
        output_policy(rules),
    )

    assert found.verdict == 'confirmed'
    assert partial.verdict == 'confirmed'


def test_unsupported_stock_statement_carries_the_domain_ground(
    rules: Any, russian_index: Any
) -> None:
    question = make_question(
        [required_claim(predicate='stock', product_id=None, stance='unknown')],
        allowed=('none',),
    )
    answer = make_answer('Бразилия Сантос есть в наличии.', kb_match='none')

    result = aggregate(
        rules, russian_index, question, answer, output_policy(rules, 'ru')
    )

    assert result.verdict == 'error'
    assert 'domain' in result.grounds


def test_service_only_field_emits_its_service_fragment(
    rules: Any, english_index: Any
) -> None:
    combined = rules.assess_field(DELIVERY_REPLY, english_index, 'customer_reply')
    alone = rules.assess_field(
        'I can pass the question to a manager.', english_index, 'customer_reply'
    )

    assert [claim.kind for claim in combined.claims] == ['absence_delivery']
    assert [
        DELIVERY_REPLY[claim.start : claim.end] for claim in combined.service_fragments
    ] == ['I can pass the question to a manager']
    assert combined.remainders == ()
    assert [claim.kind for claim in alone.claims] == ['service']
    assert [claim.kind for claim in alone.service_fragments] == ['service']


def test_forbidden_stem_in_reply_is_a_domain_error(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer('Zeolite Powder cures spring allergies.')

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        forbidden_policy(rules),
    )

    assert result.verdict == 'error'
    assert 'domain: forbidden stem cure' in result.grounds


def test_forbidden_stem_in_hint_is_a_domain_error(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer(
        'Zeolite Powder costs 18.00 USD.', hint='It treats spring allergies.'
    )

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        forbidden_policy(rules),
    )

    assert result.verdict == 'error'
    assert 'domain: forbidden stem treats' in result.grounds


def test_protected_reply_with_forbidden_stem_is_a_domain_error(
    rules: Any, english_index: Any
) -> None:
    answer = make_answer('"Zeolite Powder cures spring allergies."')

    result = aggregate(
        rules,
        english_index,
        make_question([required_claim()]),
        answer,
        forbidden_policy(rules),
    )

    assert result.verdict == 'error'
    assert 'domain: forbidden stem cure' in result.grounds


def test_forbidden_stem_policy_keeps_the_absence_templates(
    rules: Any, english_index: Any
) -> None:
    question = make_question(
        [required_claim(predicate='delivery', product_id=None, stance='unknown')],
        [required_action('handoff')],
        allowed=('none',),
    )
    answer = make_answer(DELIVERY_REPLY, kb_match='none')

    result = aggregate(rules, english_index, question, answer, forbidden_policy(rules))

    assert result.verdict == 'confirmed'
    assert result.grounds == ()


def test_handoff_only_delivery_answer_is_incomplete(
    rules: Any, english_index: Any
) -> None:
    question = make_question(
        [required_claim(predicate='delivery', product_id=None, stance='unknown')],
        [required_action('handoff')],
        allowed=('none',),
    )
    answer = make_answer('I can pass the question to a manager.', kb_match='none')

    result = aggregate(rules, english_index, question, answer, output_policy(rules))

    assert result.verdict == 'error'
    assert 'incompleteness' in result.grounds

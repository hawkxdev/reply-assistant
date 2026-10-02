"""Acceptance for issue 69."""

import asyncio
import importlib
from decimal import Decimal
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

# === Data ===

ROOT = Path(__file__).parents[2]
KB = ROOT / 'kb'


# === Fixtures and helpers ===


@pytest.fixture
def facts_module() -> ModuleType:
    """Import the fact index builder."""
    return importlib.import_module('reply_assistant.quality_facts')


def catalogue(name: str) -> Any:
    """Parse one public catalogue."""
    data = yaml.safe_load((KB / name).read_text(encoding='utf-8'))
    module = importlib.import_module('reply_assistant.knowledge_base')
    return module._document(data)


def product_facts(source_id: str) -> list[Any]:
    """Collect the annotations of one source."""
    from reply_assistant.quality_corpus import load_quality_document
    from reply_assistant.quality_schema import Facts

    raw = asyncio.run(
        load_quality_document(ROOT / 'evals' / 'quality' / 'v1' / 'facts.json')
    )
    document = raw.document
    assert isinstance(document, Facts)
    return [item for item in document.products if item.source_id == source_id]


@pytest.fixture
def english_index(facts_module: ModuleType) -> Any:
    """Build the English index."""
    return facts_module.build_fact_index(
        catalogue('example-en.yaml'), product_facts('public-en')
    )


@pytest.fixture
def russian_index(facts_module: ModuleType) -> Any:
    """Build the Russian index."""
    return facts_module.build_fact_index(
        catalogue('example-ru.yaml'), product_facts('public-ru')
    )


# === Index content ===


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
async def test_index_builds_from_both_public_sources(
    facts_module: ModuleType, english_index: Any, russian_index: Any
) -> None:
    assert set(english_index.products) == {
        'zeolite-powder-200',
        'zeolite-capsules-90',
        'clay-face-mask-100',
        'measuring-spoon',
        'travel-pill-box',
    }
    assert set(russian_index.products) == {
        'brazil-santos-250',
        'ethiopia-sidamo-250',
        'paper-filters-100',
        'hand-grinder',
    }
    powder = english_index.products['zeolite-powder-200']
    assert powder.price is not None
    assert powder.price.value == Decimal('18.00')
    assert powder.price.currency == 'USD'
    santos = russian_index.products['brazil-santos-250']
    assert santos.price is not None
    assert santos.price.value == Decimal('690')
    assert santos.price.currency == 'RUB'


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_prices_are_decimal_from_strings(english_index: Any) -> None:
    powder = english_index.products['zeolite-powder-200']

    assert powder.price is not None
    assert isinstance(powder.price.value, Decimal)
    assert str(powder.price.value) == '18.00'
    assert powder.price.value.as_tuple().exponent == -2


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_filter_size_keeps_leading_zero(russian_index: Any) -> None:
    filters = russian_index.products['paper-filters-100']

    size = filters.text('filter_size')
    assert size == '02'
    assert isinstance(size, str)


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_unresolved_role_yields_no_mass(english_index: Any, russian_index: Any) -> None:
    spoon = english_index.products['measuring-spoon']
    grinder = russian_index.products['hand-grinder']

    assert spoon.quantity_role == 'unresolved'
    assert spoon.text('object_mass') is None
    assert spoon.count('object_mass') is None
    assert spoon.support['object_mass'] == 'unresolved'
    assert grinder.quantity_role == 'batch_capacity'
    assert grinder.count('batch_capacity') == (30, 'g')
    assert grinder.support['object_mass'] == 'absent'
    assert grinder.text('object_mass') is None


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_counts_are_typed_with_units(english_index: Any) -> None:
    powder = english_index.products['zeolite-powder-200']
    box = english_index.products['travel-pill-box']

    assert powder.count('package_quantity') == (200, 'g')
    assert box.count('section_count') == (7, 'section')


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_edges_are_directed_and_complete(
    english_index: Any, russian_index: Any
) -> None:
    powder = english_index.products['zeolite-powder-200']
    spoon = english_index.products['measuring-spoon']
    santos = russian_index.products['brazil-santos-250']

    assert powder.edges == ('measuring-spoon', 'zeolite-capsules-90')
    assert spoon.edges == ()
    assert santos.edges == ('paper-filters-100', 'hand-grinder')


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_index_is_repeatable(facts_module: ModuleType, english_index: Any) -> None:
    again = facts_module.build_fact_index(
        catalogue('example-en.yaml'), product_facts('public-en')
    )

    assert again.products == english_index.products


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_products_keep_distinct_values_with_equal_support(
    facts_module: ModuleType,
) -> None:
    annotations = product_facts('public-en')
    index = facts_module.build_fact_index(catalogue('example-en.yaml'), annotations)

    first = index.products['zeolite-powder-200']
    second = index.products['zeolite-capsules-90']
    assert (first.price.value == second.price.value) is False
    assert first.support['delivery'] == second.support['delivery']


# === Inconsistent annotation ===


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_support_contradicting_fact_raises(facts_module: ModuleType) -> None:
    import copy

    from reply_assistant.quality_corpus import QualityInputError
    from reply_assistant.quality_schema import ProductFacts

    annotations = [copy.deepcopy(item) for item in product_facts('public-en')]
    powder = next(
        item for item in annotations if item.product_id == 'zeolite-powder-200'
    )
    assert isinstance(powder, ProductFacts)
    support = next(
        item for item in powder.predicate_support if item.predicate == 'goes_with'
    )
    support.status = 'absent'

    with pytest.raises(QualityInputError) as caught:
        facts_module.build_fact_index(catalogue('example-en.yaml'), annotations)

    assert caught.value.code == 'inconsistent_fact'


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_borrowed_price_value_raises(facts_module: ModuleType) -> None:
    import copy

    from reply_assistant.quality_corpus import QualityInputError
    from reply_assistant.quality_schema import ProductFacts

    annotations = [copy.deepcopy(item) for item in product_facts('public-en')]
    powder = next(
        item for item in annotations if item.product_id == 'zeolite-powder-200'
    )
    assert isinstance(powder, ProductFacts)
    price = next(item for item in powder.facts if item.predicate == 'price')
    price.value = '24.00'

    with pytest.raises(QualityInputError) as caught:
        facts_module.build_fact_index(catalogue('example-en.yaml'), annotations)

    assert caught.value.code == 'inconsistent_fact'


def synthetic_annotation() -> Any:
    """Build one annotation for a product outside the known ids."""
    from reply_assistant.quality_schema import (
        Derivation,
        Evidence,
        Fact,
        Predicate,
        ProductFacts,
        Unit,
        ValueType,
    )

    def evidence(pointer: str, start: int, end: int, quote: str) -> Evidence:
        """Build one evidence span."""
        return Evidence(pointer=pointer, start=start, end=end, quote=quote)

    def fact(
        fid: str,
        predicate: Predicate,
        value_type: ValueType,
        value: str,
        unit: Unit | None,
        derivation: Derivation,
        spans: list[Evidence],
    ) -> Fact:
        """Build one grounded fact."""
        return Fact(
            id=fid,
            predicate=predicate,
            value_type=value_type,
            value=value,
            unit=unit,
            derivation=derivation,
            evidence=spans,
        )

    facts = [
        fact(
            'mystery:name:0',
            'name',
            'text',
            'Mystery Powder',
            None,
            'literal',
            [evidence('/products/0/name', 0, 14, 'Mystery Powder')],
        ),
        fact(
            'mystery:price:0',
            'price',
            'decimal',
            '12.50',
            'USD',
            'decimal',
            [
                evidence('/products/0/price', 0, 5, '12.50'),
                evidence('/products/0/price', 6, 9, 'USD'),
            ],
        ),
        fact(
            'mystery:package:0',
            'package_quantity',
            'integer',
            '250',
            'g',
            'unit_alias',
            [
                evidence('/products/0/form', 8, 11, '250'),
                evidence('/products/0/form', 12, 13, 'g'),
            ],
        ),
    ]
    support = [
        {'predicate': 'goes_with', 'status': 'absent', 'reason': 'Empty list.'},
        {'predicate': 'delivery', 'status': 'absent', 'reason': 'No delivery.'},
    ]
    return ProductFacts.model_validate(
        {
            'source_id': 'public-en',
            'product_id': 'mystery-powder',
            'profile_id': 'F01',
            'quantity_role': 'package_quantity',
            'facts': [item.model_dump() for item in facts],
            'predicate_support': support,
        }
    )


def synthetic_catalogue() -> Any:
    """Build one catalogue with a product outside the known ids."""
    module = importlib.import_module('reply_assistant.knowledge_base')
    payload = {
        'company': 'Mystery Goods',
        'language': 'en',
        'reply_rules': ['Answer plainly.'],
        'forbidden_claims': [],
        'products': [
            {
                'id': 'mystery-powder',
                'name': 'Mystery Powder',
                'form': 'powder, 250 g jar',
                'price': '12.50 USD',
                'description': 'A synthetic product for tests.',
                'goes_with': [],
            }
        ],
        'disclaimer': None,
    }
    return module._document(payload)


@pytest.mark.xfail(strict=True, reason='E06 not implemented')
def test_synthetic_annotation_derives_without_id_branches(
    facts_module: ModuleType,
) -> None:
    index = facts_module.build_fact_index(
        synthetic_catalogue(), [synthetic_annotation()]
    )
    product = index.products['mystery-powder']

    assert product.price is not None
    assert product.price.value == Decimal('12.50')
    assert product.price.currency == 'USD'
    assert product.count('package_quantity') == (250, 'g')
    assert product.text('name') == 'Mystery Powder'
    assert product.edges == ()
    assert product.quantity_role == 'package_quantity'

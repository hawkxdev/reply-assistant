"""Typed fact index tests."""

import asyncio
import copy
import importlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from reply_assistant.quality_corpus import QualityInputError, load_quality_document
from reply_assistant.quality_schema import Facts, ProductFacts

ROOT = Path(__file__).parents[1]
FACTS_PATH = ROOT / 'evals' / 'quality' / 'v1' / 'facts.json'


def english_catalogue() -> Any:
    """Parse the English catalogue."""
    module = importlib.import_module('reply_assistant.knowledge_base')
    data = yaml.safe_load((ROOT / 'kb' / 'example-en.yaml').read_text(encoding='utf-8'))
    return module._document(data)


def english_annotations() -> list[ProductFacts]:
    """Collect the English annotations."""
    raw = asyncio.run(load_quality_document(FACTS_PATH))
    document = raw.document
    assert isinstance(document, Facts)
    return [item for item in document.products if item.source_id == 'public-en']


def powder(annotations: list[ProductFacts]) -> ProductFacts:
    """Select the powder annotation."""
    return next(item for item in annotations if item.product_id == 'zeolite-powder-200')


def build(catalogue: Any, annotations: list[ProductFacts]) -> Any:
    """Build one fact index."""
    module = importlib.import_module('reply_assistant.quality_facts')
    return module.build_fact_index(catalogue, annotations)


def test_foreign_evidence_is_rejected() -> None:
    annotations = [copy.deepcopy(item) for item in english_annotations()]
    name = next(fact for fact in powder(annotations).facts if fact.predicate == 'name')
    evidence = name.evidence[0]
    evidence.pointer = '/products/1/name'
    evidence.start = 0
    evidence.end = 16
    evidence.quote = 'Zeolite Capsules'

    with pytest.raises(QualityInputError) as caught:
        build(english_catalogue(), annotations)

    assert caught.value.code == 'invalid_evidence'


def test_unknown_product_annotation_is_rejected() -> None:
    annotations = [copy.deepcopy(item) for item in english_annotations()]
    powder(annotations).product_id = 'mystery-product'

    with pytest.raises(QualityInputError) as caught:
        build(english_catalogue(), annotations)

    assert caught.value.code == 'unknown_reference'


def test_partial_name_fact_is_rejected() -> None:
    annotations = [copy.deepcopy(item) for item in english_annotations()]
    name = next(fact for fact in powder(annotations).facts if fact.predicate == 'name')
    name.value = 'Zeolite'
    name.evidence[0].end = 7
    name.evidence[0].quote = 'Zeolite'

    with pytest.raises(QualityInputError) as caught:
        build(english_catalogue(), annotations)

    assert caught.value.code == 'inconsistent_fact'


def test_repeated_annotation_is_rejected() -> None:
    annotations = [copy.deepcopy(item) for item in english_annotations()]
    annotations.append(copy.deepcopy(powder(annotations)))

    with pytest.raises(QualityInputError) as caught:
        build(english_catalogue(), annotations)

    assert caught.value.code == 'duplicate_id'


def test_incomplete_annotation_set_is_rejected() -> None:
    annotations = [
        copy.deepcopy(item)
        for item in english_annotations()
        if item.product_id != 'travel-pill-box'
    ]

    with pytest.raises(QualityInputError) as caught:
        build(english_catalogue(), annotations)

    assert caught.value.code == 'inconsistent_fact'


# === Synthetic fixtures ===


def synthetic_catalogue() -> Any:
    """Build one catalogue with two quantities."""
    module = importlib.import_module('reply_assistant.knowledge_base')
    payload = {
        'company': 'Mystery Goods',
        'language': 'en',
        'reply_rules': ['Answer plainly.'],
        'forbidden_claims': [],
        'products': [
            {
                'id': 'duo-blend',
                'name': 'Duo Blend',
                'form': 'powder, 200 g jar',
                'price': '12.50 USD',
                'description': 'Add 5 g of water.',
                'goes_with': [],
            }
        ],
        'disclaimer': None,
    }
    return module._document(payload)


def synthetic_payload() -> list[dict[str, Any]]:
    """Build conflicting quantity annotations."""
    return [
        {
            'id': 'duo:name:0',
            'predicate': 'name',
            'value_type': 'text',
            'value': 'Duo Blend',
            'unit': None,
            'derivation': 'literal',
            'evidence': [
                {
                    'pointer': '/products/0/name',
                    'start': 0,
                    'end': 9,
                    'quote': 'Duo Blend',
                }
            ],
        },
        {
            'id': 'duo:price:0',
            'predicate': 'price',
            'value_type': 'decimal',
            'value': '12.50',
            'unit': 'USD',
            'derivation': 'decimal',
            'evidence': [
                {
                    'pointer': '/products/0/price',
                    'start': 0,
                    'end': 5,
                    'quote': '12.50',
                },
                {
                    'pointer': '/products/0/price',
                    'start': 6,
                    'end': 9,
                    'quote': 'USD',
                },
            ],
        },
        {
            'id': 'duo:package:0',
            'predicate': 'package_quantity',
            'value_type': 'integer',
            'value': '200',
            'unit': 'g',
            'derivation': 'unit_alias',
            'evidence': [
                {
                    'pointer': '/products/0/form',
                    'start': 8,
                    'end': 11,
                    'quote': '200',
                },
                {
                    'pointer': '/products/0/form',
                    'start': 12,
                    'end': 13,
                    'quote': 'g',
                },
            ],
        },
        {
            'id': 'duo:package:1',
            'predicate': 'package_quantity',
            'value_type': 'integer',
            'value': '5',
            'unit': 'g',
            'derivation': 'unit_alias',
            'evidence': [
                {
                    'pointer': '/products/0/description',
                    'start': 4,
                    'end': 5,
                    'quote': '5',
                },
                {
                    'pointer': '/products/0/description',
                    'start': 6,
                    'end': 7,
                    'quote': 'g',
                },
            ],
        },
    ]


def synthetic_annotation(payload: list[dict[str, Any]]) -> ProductFacts:
    """Validate one synthetic annotation."""
    return ProductFacts.model_validate(
        {
            'source_id': 'public-en',
            'product_id': 'duo-blend',
            'profile_id': 'F01',
            'quantity_role': 'package_quantity',
            'facts': payload,
            'predicate_support': [
                {
                    'predicate': 'goes_with',
                    'status': 'absent',
                    'reason': 'Empty list.',
                },
                {
                    'predicate': 'delivery',
                    'status': 'absent',
                    'reason': 'No delivery.',
                },
            ],
        }
    )


def test_conflicting_counts_are_rejected() -> None:
    annotation = synthetic_annotation(synthetic_payload())

    with pytest.raises(QualityInputError) as caught:
        build(synthetic_catalogue(), [annotation])

    assert caught.value.code == 'inconsistent_fact'

"""Typed fact index tests."""

import asyncio
import copy
import importlib
from pathlib import Path
from typing import Any

import pytest
import yaml

from reply_assistant.quality_corpus import QualityInputError, load_quality_document
from reply_assistant.quality_schema import Fact, Facts, ProductFacts

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


def spoon(annotations: list[ProductFacts]) -> ProductFacts:
    """Select the spoon annotation."""
    return next(item for item in annotations if item.product_id == 'measuring-spoon')


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


def test_missing_retained_fact_is_rejected() -> None:
    annotations = [copy.deepcopy(item) for item in english_annotations()]
    profile = powder(annotations)
    profile.facts = [fact for fact in profile.facts if fact.predicate != 'form']

    with pytest.raises(QualityInputError) as caught:
        build(english_catalogue(), annotations)

    assert caught.value.code == 'inconsistent_fact'


def test_contradicting_profile_components_are_rejected() -> None:
    annotations = [copy.deepcopy(item) for item in english_annotations()]
    powder(annotations).profile_id = 'F06'

    with pytest.raises(QualityInputError) as caught:
        build(english_catalogue(), annotations)

    assert caught.value.code == 'inconsistent_fact'


def test_contradicting_profile_role_is_rejected() -> None:
    annotations = [copy.deepcopy(item) for item in english_annotations()]
    spoon(annotations).quantity_role = 'package_quantity'

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


# === Relation binding fixtures ===


def relation_catalogue() -> Any:
    """Build one edge catalogue."""
    module = importlib.import_module('reply_assistant.knowledge_base')
    payload = {
        'company': 'Edge Goods',
        'language': 'en',
        'reply_rules': ['Answer plainly.'],
        'forbidden_claims': [],
        'products': [
            {
                'id': 'beta-blend',
                'name': 'beta blend mixer',
                'form': 'powder, 100 g jar',
                'price': '5.00 USD',
                'description': 'Add 5 g per cup.',
                'goes_with': ['beta'],
            },
            {
                'id': 'beta',
                'name': 'Beta',
                'form': 'capsules, 30 pieces',
                'price': '3.00 USD',
                'description': 'Thirty beta capsules.',
                'goes_with': [],
            },
        ],
        'disclaimer': None,
    }
    return module._document(payload)


def relation_payloads() -> list[dict[str, Any]]:
    """Build two bound annotations."""
    return [
        {
            'source_id': 'public-en',
            'product_id': 'beta-blend',
            'profile_id': 'F01',
            'quantity_role': 'package_quantity',
            'facts': [
                {
                    'id': 'edge:name:0',
                    'predicate': 'name',
                    'value_type': 'text',
                    'value': 'beta blend mixer',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/0/name',
                            'start': 0,
                            'end': 16,
                            'quote': 'beta blend mixer',
                        }
                    ],
                },
                {
                    'id': 'edge:form:0',
                    'predicate': 'form',
                    'value_type': 'text',
                    'value': 'powder, 100 g jar',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/0/form',
                            'start': 0,
                            'end': 17,
                            'quote': 'powder, 100 g jar',
                        }
                    ],
                },
                {
                    'id': 'edge:description:0',
                    'predicate': 'description',
                    'value_type': 'text',
                    'value': 'Add 5 g per cup.',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/0/description',
                            'start': 0,
                            'end': 16,
                            'quote': 'Add 5 g per cup.',
                        }
                    ],
                },
                {
                    'id': 'edge:price:0',
                    'predicate': 'price',
                    'value_type': 'decimal',
                    'value': '5.00',
                    'unit': 'USD',
                    'derivation': 'decimal',
                    'evidence': [
                        {
                            'pointer': '/products/0/price',
                            'start': 0,
                            'end': 4,
                            'quote': '5.00',
                        },
                        {
                            'pointer': '/products/0/price',
                            'start': 5,
                            'end': 8,
                            'quote': 'USD',
                        },
                    ],
                },
                {
                    'id': 'edge:form_kind:0',
                    'predicate': 'form_kind',
                    'value_type': 'text',
                    'value': 'powder',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/0/form',
                            'start': 0,
                            'end': 6,
                            'quote': 'powder',
                        }
                    ],
                },
                {
                    'id': 'edge:container:0',
                    'predicate': 'container',
                    'value_type': 'text',
                    'value': 'jar',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/0/form',
                            'start': 14,
                            'end': 17,
                            'quote': 'jar',
                        }
                    ],
                },
                {
                    'id': 'edge:package:0',
                    'predicate': 'package_quantity',
                    'value_type': 'integer',
                    'value': '100',
                    'unit': 'g',
                    'derivation': 'unit_alias',
                    'evidence': [
                        {
                            'pointer': '/products/0/form',
                            'start': 8,
                            'end': 11,
                            'quote': '100',
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
                    'id': 'edge:goes_with:0',
                    'predicate': 'goes_with',
                    'value_type': 'reference',
                    'value': 'beta',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/0/goes_with/0',
                            'start': 0,
                            'end': 4,
                            'quote': 'beta',
                        }
                    ],
                },
            ],
            'predicate_support': [
                {
                    'predicate': 'goes_with',
                    'status': 'supported',
                    'reason': 'Listed edge.',
                },
                {
                    'predicate': 'delivery',
                    'status': 'absent',
                    'reason': 'No delivery.',
                },
            ],
        },
        {
            'source_id': 'public-en',
            'product_id': 'beta',
            'profile_id': 'F02',
            'quantity_role': 'package_quantity',
            'facts': [
                {
                    'id': 'base:name:0',
                    'predicate': 'name',
                    'value_type': 'text',
                    'value': 'Beta',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/1/name',
                            'start': 0,
                            'end': 4,
                            'quote': 'Beta',
                        }
                    ],
                },
                {
                    'id': 'base:form:0',
                    'predicate': 'form',
                    'value_type': 'text',
                    'value': 'capsules, 30 pieces',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/1/form',
                            'start': 0,
                            'end': 19,
                            'quote': 'capsules, 30 pieces',
                        }
                    ],
                },
                {
                    'id': 'base:description:0',
                    'predicate': 'description',
                    'value_type': 'text',
                    'value': 'Thirty beta capsules.',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/1/description',
                            'start': 0,
                            'end': 21,
                            'quote': 'Thirty beta capsules.',
                        }
                    ],
                },
                {
                    'id': 'base:price:0',
                    'predicate': 'price',
                    'value_type': 'decimal',
                    'value': '3.00',
                    'unit': 'USD',
                    'derivation': 'decimal',
                    'evidence': [
                        {
                            'pointer': '/products/1/price',
                            'start': 0,
                            'end': 4,
                            'quote': '3.00',
                        },
                        {
                            'pointer': '/products/1/price',
                            'start': 5,
                            'end': 8,
                            'quote': 'USD',
                        },
                    ],
                },
                {
                    'id': 'base:form_kind:0',
                    'predicate': 'form_kind',
                    'value_type': 'text',
                    'value': 'capsules',
                    'unit': None,
                    'derivation': 'literal',
                    'evidence': [
                        {
                            'pointer': '/products/1/form',
                            'start': 0,
                            'end': 8,
                            'quote': 'capsules',
                        }
                    ],
                },
                {
                    'id': 'base:package:0',
                    'predicate': 'package_quantity',
                    'value_type': 'integer',
                    'value': '30',
                    'unit': 'piece',
                    'derivation': 'unit_alias',
                    'evidence': [
                        {
                            'pointer': '/products/1/form',
                            'start': 10,
                            'end': 12,
                            'quote': '30',
                        },
                        {
                            'pointer': '/products/1/form',
                            'start': 13,
                            'end': 19,
                            'quote': 'pieces',
                        },
                    ],
                },
            ],
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
        },
    ]


def relation_annotations() -> list[ProductFacts]:
    """Validate two bound annotations."""
    return [ProductFacts.model_validate(payload) for payload in relation_payloads()]


def test_relation_evidence_outside_edge_is_rejected() -> None:
    annotations = relation_annotations()
    edge = next(fact for fact in annotations[0].facts if fact.predicate == 'goes_with')
    edge.evidence[0].pointer = '/products/0/name'

    with pytest.raises(QualityInputError) as caught:
        build(relation_catalogue(), annotations)

    assert caught.value.code == 'invalid_evidence'


def test_foreign_form_quantity_is_rejected() -> None:
    annotations = relation_annotations()
    annotations[0].facts.append(
        Fact.model_validate(
            {
                'id': 'edge:portion:0',
                'predicate': 'form_quantity',
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
            }
        )
    )

    with pytest.raises(QualityInputError) as caught:
        build(relation_catalogue(), annotations)

    assert caught.value.code == 'inconsistent_fact'

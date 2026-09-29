"""Acceptance for issue 14."""

import importlib
from pathlib import Path
from textwrap import dedent
from types import ModuleType

import pytest

# === Data ===

KB = Path(__file__).parents[2] / 'kb'
VALID = """
    company: Box Shop
    language: en
    reply_rules:
      - Answer briefly.
    forbidden_claims:
      - cure
    products:
      - id: box
        name: Box
        form: cardboard
        price: 2.00 USD
        description: A plain box.
        goes_with:
          - tape
      - id: tape
        name: Tape
        form: roll
        price: 1.00 USD
        description: Sticky tape.
"""

# === Fixtures and helpers ===


@pytest.fixture
def kb_module() -> ModuleType:
    """Import the knowledge base module."""
    return importlib.import_module('reply_assistant.knowledge_base')


def write(directory: Path, text: str) -> Path:
    """Write a knowledge base file."""
    path = directory / 'kb.yaml'
    path.write_text(dedent(text).lstrip(), encoding='utf-8')
    return path


# === Example files ===


@pytest.mark.parametrize(
    ('name', 'company', 'language', 'ids'),
    [
        (
            'example-en.yaml',
            'Clayfield Minerals',
            'en',
            [
                'zeolite-powder-200',
                'zeolite-capsules-90',
                'clay-face-mask-100',
                'measuring-spoon',
                'travel-pill-box',
            ],
        ),
        (
            'example-ru.yaml',
            "Обжарочная 'Зерно'",
            'ru',
            [
                'brazil-santos-250',
                'ethiopia-sidamo-250',
                'paper-filters-100',
                'hand-grinder',
            ],
        ),
    ],
    ids=['en', 'ru'],
)
async def test_example_file_loads(
    kb_module: ModuleType, name: str, company: str, language: str, ids: list[str]
) -> None:
    kb = await kb_module.load_knowledge_base(KB / name)

    assert kb.company == company
    assert kb.language == language
    assert [product.id for product in kb.products] == ids


async def test_product_fields_are_kept_verbatim(kb_module: ModuleType) -> None:
    kb = await kb_module.load_knowledge_base(KB / 'example-en.yaml')
    powder = kb.products[0]

    assert powder.name == 'Zeolite Powder'
    assert powder.form == 'powder, 200 g jar'
    assert powder.price == '18.00 USD'
    assert powder.description == (
        'Finely milled natural zeolite for daily use with water.'
    )
    assert powder.goes_with == ['measuring-spoon', 'zeolite-capsules-90']


async def test_rules_and_stems_are_kept(kb_module: ModuleType) -> None:
    kb = await kb_module.load_knowledge_base(KB / 'example-en.yaml')

    assert kb.reply_rules[0] == (
        'Answer in two to four sentences, in a polite and plain tone.'
    )
    assert kb.forbidden_claims == [
        ' cure',
        ' curing',
        'heal ',
        'heals',
        'healed',
        'healing',
        'treat ',
        'treats',
        'treated',
        'treating',
        'diagnos',
        'recover',
        'clinically',
        'instead of medicine',
    ]


async def test_disclaimer_is_optional(kb_module: ModuleType) -> None:
    english = await kb_module.load_knowledge_base(KB / 'example-en.yaml')
    russian = await kb_module.load_knowledge_base(KB / 'example-ru.yaml')

    assert english.disclaimer == (
        'This product is a food supplement and is not a medicine.'
    )
    assert russian.disclaimer is None


async def test_goes_with_is_empty_when_absent(
    kb_module: ModuleType, tmp_path: Path
) -> None:
    kb = await kb_module.load_knowledge_base(write(tmp_path, VALID))

    assert kb.products[1].goes_with == []


# === Invalid files ===


@pytest.mark.parametrize(
    ('old', 'new', 'field'),
    [
        ('company: Box Shop\n', '', 'company'),
        ('    price: 2.00 USD\n', '', 'products.0.price'),
        ('    name: Box\n', "    name: ''\n", 'products.0.name'),
        ('    price: 2.00 USD\n', '    price: 2\n', 'products.0.price'),
        ('language: en\n', 'language: en\ncolour: red\n', 'colour'),
        ('    form: roll\n', '    form: roll\n    colour: red\n', 'products.1.colour'),
        ('  - id: tape\n', '  - id: box\n', 'products.1.id'),
        ('      - tape\n', '      - glue\n', 'products.0.goes_with'),
    ],
    ids=[
        'missing company',
        'missing price',
        'empty name',
        'number as price',
        'unknown key',
        'unknown product key',
        'duplicate id',
        'unknown related product',
    ],
)
async def test_invalid_file_names_the_field(
    kb_module: ModuleType, tmp_path: Path, old: str, new: str, field: str
) -> None:
    text = dedent(VALID).lstrip()
    assert text.count(old) == 1
    path = tmp_path / 'kb.yaml'
    path.write_text(text.replace(old, new), encoding='utf-8')

    with pytest.raises(kb_module.KnowledgeBaseError) as caught:
        await kb_module.load_knowledge_base(path)

    assert caught.value.field == field
    assert field in str(caught.value)


async def test_empty_product_list_is_rejected(
    kb_module: ModuleType, tmp_path: Path
) -> None:
    text = dedent(VALID).lstrip().split('products:')[0] + 'products: []\n'

    with pytest.raises(kb_module.KnowledgeBaseError) as caught:
        await kb_module.load_knowledge_base(write(tmp_path, text))

    assert caught.value.field == 'products'


@pytest.mark.parametrize(
    'text',
    ['company: [unclosed\n', '- a list\n- not a mapping\n'],
    ids=['yaml', 'list'],
)
async def test_unreadable_file_is_rejected(
    kb_module: ModuleType, tmp_path: Path, text: str
) -> None:
    with pytest.raises(kb_module.KnowledgeBaseError) as caught:
        await kb_module.load_knowledge_base(write(tmp_path, text))

    assert caught.value.field is None


async def test_missing_file_is_rejected(kb_module: ModuleType, tmp_path: Path) -> None:
    path = tmp_path / 'absent.yaml'

    with pytest.raises(kb_module.KnowledgeBaseError) as caught:
        await kb_module.load_knowledge_base(path)

    assert caught.value.field is None
    assert str(path) in str(caught.value)

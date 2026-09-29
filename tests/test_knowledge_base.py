"""Knowledge base loader unit tests."""

import threading
from pathlib import Path
from textwrap import dedent
from typing import Any

import pytest
import yaml

from reply_assistant.knowledge_base import KnowledgeBaseError, load_knowledge_base

# === Data ===

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

BOX = """\
  - id: box
    name: Box
    form: cardboard
    price: 2.00 USD
    description: A plain box.
    goes_with:
      - tape
"""

# === Helpers ===


def write(directory: Path, text: str) -> Path:
    """Write a knowledge base file."""
    path = directory / 'kb.yaml'
    path.write_text(text, encoding='utf-8')
    return path


def edit(old: str, new: str) -> str:
    """Apply one replacement to the template."""
    base = dedent(VALID).lstrip()
    assert base.count(old) == 1
    return base.replace(old, new)


# === Tests ===


@pytest.mark.parametrize(
    ('old', 'new', 'field'),
    [
        ('  - Answer briefly.\n', '  - 2\n', 'reply_rules.0'),
        ('  - cure\n', "  - ''\n", 'forbidden_claims.0'),
    ],
    ids=['rule is a number', 'stem is empty'],
)
async def test_text_list_entry_is_rejected(
    tmp_path: Path, old: str, new: str, field: str
) -> None:
    with pytest.raises(KnowledgeBaseError) as caught:
        await load_knowledge_base(write(tmp_path, edit(old, new)))

    assert caught.value.field == field
    assert field in str(caught.value)


async def test_disclaimer_that_is_not_text_is_rejected(tmp_path: Path) -> None:
    text = edit('language: en\n', 'language: en\ndisclaimer: 3\n')

    with pytest.raises(KnowledgeBaseError) as caught:
        await load_knowledge_base(write(tmp_path, text))

    assert caught.value.field == 'disclaimer'


@pytest.mark.parametrize(
    ('old', 'new', 'field'),
    [
        (BOX, '  - box\n', 'products.0'),
        (
            '    goes_with:\n      - tape\n',
            '    goes_with: 2\n',
            'products.0.goes_with',
        ),
        (
            '    goes_with:\n      - tape\n',
            '    goes_with: null\n',
            'products.0.goes_with',
        ),
    ],
    ids=['product is text', 'goes_with is a number', 'goes_with is null'],
)
async def test_value_of_wrong_shape_is_rejected(
    tmp_path: Path, old: str, new: str, field: str
) -> None:
    with pytest.raises(KnowledgeBaseError) as caught:
        await load_knowledge_base(write(tmp_path, edit(old, new)))

    assert caught.value.field == field


async def test_products_that_is_not_a_list_is_rejected(tmp_path: Path) -> None:
    base = dedent(VALID).lstrip()
    text = base.split('products:')[0] + 'products: box\n'

    with pytest.raises(KnowledgeBaseError) as caught:
        await load_knowledge_base(write(tmp_path, text))

    assert caught.value.field == 'products'


async def test_parsing_runs_off_the_event_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loop_thread = threading.get_ident()
    parser_threads = []
    original = yaml.safe_load

    def spy(text: str) -> Any:
        """Parse text and note the thread."""
        parser_threads.append(threading.get_ident())
        return original(text)

    monkeypatch.setattr(yaml, 'safe_load', spy)

    await load_knowledge_base(write(tmp_path, dedent(VALID).lstrip()))

    assert parser_threads[0] != loop_thread

"""Checks unit tests."""

from pathlib import Path

import pytest

from reply_assistant.checks import (
    CheckError,
    check_no_forbidden_claim,
    check_product_exists,
)
from reply_assistant.knowledge_base import load_knowledge_base
from reply_assistant.suggestion import ModelOutput

# === Data ===

KB_FILE = Path(__file__).parents[1] / 'kb' / 'example-en.yaml'

# === Helpers ===


def output(
    reply: str = 'Here is the answer.', product: str | None = None
) -> ModelOutput:
    """Build one model output."""
    return ModelOutput(
        customer_reply=reply,
        upsell_product_id=product,
        upsell_hint='Nothing extra to offer.',
        kb_match='none',
    )


# === Tests ===


async def test_prefix_of_a_product_id_is_rejected() -> None:
    kb = await load_knowledge_base(KB_FILE)

    with pytest.raises(CheckError) as caught:
        check_product_exists(output(product='measuring-spo'), kb)

    assert caught.value.check == 'product_exists'
    assert 'measuring-spo' in str(caught.value)


async def test_two_separators_do_not_close_on_a_stem() -> None:
    kb = await load_knowledge_base(KB_FILE)

    result = check_no_forbidden_claim(  # type: ignore[func-returns-value]
        output(reply='Effective, treatment!'), kb
    )

    assert result is None


async def test_underscore_separates_words() -> None:
    kb = await load_knowledge_base(KB_FILE)

    with pytest.raises(CheckError) as caught:
        check_no_forbidden_claim(output(reply='We treat_people kindly.'), kb)

    assert caught.value.check == 'no_forbidden_claim'

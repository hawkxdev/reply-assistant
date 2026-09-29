"""Acceptance for issue 19."""

import importlib
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

pytestmark = pytest.mark.xfail(strict=True, reason='issue 19 is not implemented')

# === Data ===

KB = Path(__file__).parents[2] / 'kb'
REPLY = 'Yes, we ship the powder to Minsk.'
HINT = 'Offer the spoon that measures one serving.'
SAFE_HEALTH_REPLY = (
    'For questions about your health, please ask your doctor. '
    'We accept secure payment by card. This is a food supplement, not a treatment.'
)

# === Fixtures and helpers ===


@pytest.fixture
def checks() -> ModuleType:
    """Import the checks module."""
    return importlib.import_module('reply_assistant.checks')


async def load(name: str) -> Any:
    """Load an example file."""
    module = importlib.import_module('reply_assistant.knowledge_base')
    return await module.load_knowledge_base(KB / name)


def output(
    reply: str = REPLY, product: str | None = 'measuring-spoon', hint: str = HINT
) -> Any:
    """Build a model output."""
    module = importlib.import_module('reply_assistant.suggestion')
    return module.ModelOutput(
        customer_reply=reply,
        upsell_product_id=product,
        upsell_hint=hint,
        kb_match='found',
    )


# === Product exists ===


@pytest.mark.parametrize(
    'product', ['travel-pill-box', None], ids=['last product', 'none']
)
async def test_known_or_no_product_passes(
    checks: ModuleType, product: str | None
) -> None:
    kb = await load('example-en.yaml')

    assert checks.check_product_exists(output(product=product), kb) is None


@pytest.mark.parametrize(
    'product', ['glue', 'MEASURING-SPOON'], ids=['unknown', 'case']
)
async def test_other_product_is_rejected(checks: ModuleType, product: str) -> None:
    kb = await load('example-en.yaml')

    with pytest.raises(checks.CheckFailed) as caught:
        checks.check_product_exists(output(product=product), kb)

    assert caught.value.check == 'product_exists'
    assert product in str(caught.value)


# === No forbidden claim ===


@pytest.mark.parametrize(
    ('reply', 'hint', 'stem', 'field'),
    [
        ('This powder cures allergies.', HINT, 'cures', 'customer_reply'),
        (REPLY, 'Say it is clinically proven.', 'clinically', 'upsell_hint'),
        ('THIS POWDER CURES ALLERGIES.', HINT, 'cures', 'customer_reply'),
        ('Faster recovery after a cold.', HINT, 'recover', 'customer_reply'),
    ],
    ids=['reply', 'hint', 'upper case', 'inside a word'],
)
async def test_forbidden_claim_is_rejected(
    checks: ModuleType, reply: str, hint: str, stem: str, field: str
) -> None:
    kb = await load('example-en.yaml')

    with pytest.raises(checks.CheckFailed) as caught:
        checks.check_no_forbidden_claim(output(reply=reply, hint=hint), kb)

    assert caught.value.check == 'no_forbidden_claim'
    assert stem in str(caught.value)
    assert field in str(caught.value)


async def test_cyrillic_claim_is_rejected_without_regard_to_case(
    checks: ModuleType,
) -> None:
    kb = await load('example-ru.yaml')
    reply = 'Этот кофе ЛЕЧИТ бессонницу.'

    with pytest.raises(checks.CheckFailed) as caught:
        checks.check_no_forbidden_claim(output(reply=reply, product=None), kb)

    assert caught.value.check == 'no_forbidden_claim'


async def test_example_stems_allow_a_safe_health_reply(checks: ModuleType) -> None:
    kb = await load('example-en.yaml')

    assert checks.check_no_forbidden_claim(output(reply=SAFE_HEALTH_REPLY), kb) is None


# === Disclaimer ===


async def test_disclaimer_is_appended(checks: ModuleType) -> None:
    kb = await load('example-en.yaml')

    assert checks.append_disclaimer(REPLY, kb) == (
        f'{REPLY}\n\nThis product is a food supplement and is not a medicine.'
    )


async def test_reply_is_unchanged_without_disclaimer(checks: ModuleType) -> None:
    kb = await load('example-ru.yaml')

    assert checks.append_disclaimer(REPLY, kb) == REPLY

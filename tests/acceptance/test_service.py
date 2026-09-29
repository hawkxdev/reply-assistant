"""Acceptance for issue 25."""

import importlib
import json
from pathlib import Path
from types import ModuleType

import pytest

from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from reply_assistant.model_client import ProviderError
from reply_assistant.prompt import build_messages
from reply_assistant.suggestion import SuggestionRequest, output_schema
from tests.acceptance.fakes import FakeModelClient

pytestmark = pytest.mark.xfail(strict=True, reason='issue 25 is not implemented')

# === Data ===

KB = Path(__file__).parents[2] / 'kb'
MESSAGE = 'Do you ship the powder to Minsk?'
VALID = {
    'customer_reply': 'Yes, we ship the powder to Minsk.',
    'upsell_product_id': 'measuring-spoon',
    'upsell_hint': 'Offer the spoon that measures one serving.',
    'kb_match': 'found',
}
VALID_RU = {
    'customer_reply': 'Да, отправим в Минск.',
    'upsell_product_id': 'hand-grinder',
    'upsell_hint': 'Предложите кофемолку.',
    'kb_match': 'partial',
}
DISCLAIMER = 'This product is a food supplement and is not a medicine.'
RETRY_RULE = (
    'The previous answer was rejected by the check {check}. '
    'Answer again and follow every rule.'
)
REJECTED = {
    'shape': 'Yes, we ship it.',
    'product_exists': json.dumps(
        {
            'customer_reply': 'We ship it tomorrow.',
            'upsell_product_id': 'glue',
            'upsell_hint': 'Offer the glue.',
            'kb_match': 'partial',
        }
    ),
    'no_forbidden_claim': json.dumps(
        {**VALID, 'customer_reply': 'This powder cures allergies.'}
    ),
}

# === Fixtures and helpers ===


@pytest.fixture
def service() -> ModuleType:
    """Import the service module."""
    return importlib.import_module('reply_assistant.service')


@pytest.fixture
async def kb() -> KnowledgeBase:
    """Load the English example."""
    return await load_knowledge_base(KB / 'example-en.yaml')


def request() -> SuggestionRequest:
    """Build the customer request."""
    return SuggestionRequest(message=MESSAGE)


# === One attempt ===


async def test_valid_answer_becomes_the_suggestion(
    service: ModuleType, kb: KnowledgeBase
) -> None:
    fake = FakeModelClient([json.dumps(VALID)])

    result = await service.suggest(request(), kb, fake)

    assert result.customer_reply == f'{VALID["customer_reply"]}\n\n{DISCLAIMER}'
    assert result.upsell_product_id == 'measuring-spoon'
    assert result.upsell_hint == VALID['upsell_hint']
    assert result.kb_match == 'found'


async def test_report_of_one_attempt(service: ModuleType, kb: KnowledgeBase) -> None:
    fake = FakeModelClient([json.dumps(VALID)])

    result = await service.suggest(request(), kb, fake)

    assert result.checks.rejected == []
    assert result.checks.disclaimer_appended is True
    assert result.usage.input_tokens == 100
    assert result.usage.output_tokens == 20
    assert result.usage.provider == 'fake'
    assert result.usage.attempts == 1


async def test_reply_without_disclaimer_is_unchanged(service: ModuleType) -> None:
    kb = await load_knowledge_base(KB / 'example-ru.yaml')
    fake = FakeModelClient([json.dumps(VALID_RU)])

    result = await service.suggest(request(), kb, fake)

    assert result.customer_reply == VALID_RU['customer_reply']
    assert result.checks.disclaimer_appended is False


# === Retry ===


@pytest.mark.parametrize('check', list(REJECTED))
async def test_rejected_answer_is_retried_once(
    service: ModuleType, kb: KnowledgeBase, check: str
) -> None:
    fake = FakeModelClient([REJECTED[check], json.dumps(VALID)])

    result = await service.suggest(request(), kb, fake)

    assert result.checks.rejected == [check]
    assert result.customer_reply.startswith(VALID['customer_reply'])
    assert result.upsell_product_id == VALID['upsell_product_id']
    assert result.upsell_hint == VALID['upsell_hint']
    assert result.kb_match == VALID['kb_match']
    assert result.usage.attempts == 2
    assert result.usage.input_tokens == 300
    assert result.usage.output_tokens == 60
    assert fake.calls == [
        (build_messages(kb, MESSAGE), output_schema(kb)),
        (
            [
                *build_messages(kb, MESSAGE),
                {'role': 'system', 'content': RETRY_RULE.format(check=check)},
            ],
            output_schema(kb),
        ),
    ]


async def test_second_rejection_is_an_error_with_the_check(
    service: ModuleType, kb: KnowledgeBase
) -> None:
    fake = FakeModelClient([REJECTED['shape'], REJECTED['product_exists']])

    with pytest.raises(service.SuggestionRejectedError) as caught:
        await service.suggest(request(), kb, fake)

    assert caught.value.check == 'product_exists'
    assert 'product_exists' in str(caught.value)
    assert len(fake.calls) == 2


async def test_provider_error_is_not_retried(
    service: ModuleType, kb: KnowledgeBase
) -> None:
    fake = FakeModelClient(
        [
            ProviderError(provider='fake', kind='server', message='down'),
            json.dumps(VALID),
        ]
    )

    with pytest.raises(ProviderError) as caught:
        await service.suggest(request(), kb, fake)

    assert caught.value.kind == 'server'
    assert len(fake.calls) == 1

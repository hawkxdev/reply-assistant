"""Service unit tests."""

import json
from pathlib import Path
from typing import Any

from reply_assistant.knowledge_base import load_knowledge_base
from reply_assistant.model_client import Completion, ModelClient, Usage
from reply_assistant.service import suggest
from reply_assistant.suggestion import SuggestionRequest
from tests.acceptance.fakes import FakeModelClient

# === Data ===

KB_FILE = Path(__file__).parents[1] / 'kb' / 'example-en.yaml'
MESSAGE = 'Do you ship the powder to Minsk?'
VALID = {
    'customer_reply': 'Yes, we ship the powder to Minsk.',
    'upsell_product_id': 'measuring-spoon',
    'upsell_hint': 'Offer the spoon that measures one serving.',
    'kb_match': 'found',
}
DOUBLE_FAILURE = json.dumps(
    {
        'customer_reply': 'This powder cures allergies.',
        'upsell_product_id': 'glue',
        'upsell_hint': 'Offer the glue.',
        'kb_match': 'partial',
    }
)


class SwitchingProviderClient:
    """Client that names a new provider each call."""

    def __init__(self, replies: list[str]) -> None:
        """Keep the scripted replies."""
        self.replies = list(replies)
        self.calls = 0

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return one completion."""
        self.calls += 1
        return Completion(
            text=self.replies.pop(0),
            usage=Usage(
                input_tokens=1,
                output_tokens=1,
                provider=f'provider-{self.calls}',
            ),
        )


class AlwaysSwitchingClient:
    """Return successive provider switches."""

    def __init__(self, replies: list[str]) -> None:
        """Keep the scripted replies."""
        self.replies = list(replies)
        self.switches = 0

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return one switched completion."""
        self.switches += 1
        return Completion(
            text=self.replies.pop(0),
            usage=Usage(
                1,
                1,
                f'second-{self.switches}.test',
                fallback_from=f'first-{self.switches}.test',
            ),
        )


# === Tests ===


async def test_first_failing_check_names_the_retry() -> None:
    kb = await load_knowledge_base(KB_FILE)
    fake = FakeModelClient([DOUBLE_FAILURE, json.dumps(VALID)])

    result = await suggest(SuggestionRequest(message=MESSAGE), kb, fake)

    assert result.checks.rejected == ['product_exists']
    assert fake.calls[1][0][-1] == {
        'role': 'system',
        'content': (
            'The previous answer was rejected by the check product_exists. '
            'Answer again and follow every rule.'
        ),
    }


async def test_usage_names_the_provider_of_the_last_completion() -> None:
    kb = await load_knowledge_base(KB_FILE)
    client = SwitchingProviderClient(['not json', json.dumps(VALID)])

    result = await suggest(SuggestionRequest(message=MESSAGE), kb, client)

    assert client.calls == 2
    assert result.usage.provider == 'provider-2'


async def test_usage_keeps_every_switch_in_order() -> None:
    kb = await load_knowledge_base(KB_FILE)
    client = AlwaysSwitchingClient([DOUBLE_FAILURE, json.dumps(VALID)])

    result = await suggest(SuggestionRequest(message=MESSAGE), kb, client)

    assert result.usage.model_dump()['fallbacks'] == [
        {'primary': 'first-1.test', 'secondary': 'second-1.test'},
        {'primary': 'first-2.test', 'secondary': 'second-2.test'},
    ]


_conforms: ModelClient = SwitchingProviderClient([])

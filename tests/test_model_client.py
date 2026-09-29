"""Model client unit tests."""

import httpx2
import pytest
from pydantic import SecretStr

from reply_assistant.model_client import OpenAICompatibleClient, ProviderError

# === Data ===

BASE_URL = 'https://llm.example.test/v1'
KEY = 'unit-key-4b1d'
MESSAGES = [{'role': 'user', 'content': 'Is the box in stock?'}]
SCHEMA = {'type': 'object', 'properties': {}}
BODY_MARK = 'leaked body marker 8e31'


# === Helpers ===


def answering(response: httpx2.Response) -> httpx2.MockTransport:
    """Answer every request the same."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        """Return the canned response."""
        return response

    return httpx2.MockTransport(handle)


def client(transport: httpx2.MockTransport) -> OpenAICompatibleClient:
    """Build the tested client."""
    return OpenAICompatibleClient(
        base_url=BASE_URL,
        api_key=SecretStr(KEY),
        model='test-model',
        transport=transport,
    )


# === Tests ===


async def test_malformed_reply_message_hides_the_body() -> None:
    response = httpx2.Response(200, json={'unexpected': BODY_MARK})

    with pytest.raises(ProviderError) as caught:
        await client(answering(response)).complete(MESSAGES, SCHEMA)

    assert BODY_MARK not in str(caught.value)
    assert BODY_MARK not in repr(caught.value)


async def test_other_transport_error_is_a_connection_error() -> None:
    def handle(request: httpx2.Request) -> httpx2.Response:
        """Drop the connection."""
        raise httpx2.ReadError('reset by peer')

    with pytest.raises(ProviderError) as caught:
        await client(httpx2.MockTransport(handle)).complete(MESSAGES, SCHEMA)

    assert caught.value.kind == 'connection'

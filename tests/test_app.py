"""Application factory tests."""

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from tests.acceptance.fakes import FakeModelClient

# === Data ===

KB = Path(__file__).parents[1] / 'kb'
ENV = {
    'REPLY_ASSISTANT_PROVIDER_API_KEY': 'test-key',
    'REPLY_ASSISTANT_PROVIDER_BASE_URL': 'https://llm.example.test/v1',
    'REPLY_ASSISTANT_PROVIDER_MODEL': 'test-model',
    'REPLY_ASSISTANT_KB_PATH': str(KB / 'example-en.yaml'),
}
MESSAGE = 'Do you ship the powder to Minsk?'
DISCLAIMER = 'This product is a food supplement and is not a medicine.'
REPLY = json.dumps(
    {
        'customer_reply': 'Yes, we ship the powder to Minsk.',
        'upsell_product_id': None,
        'upsell_hint': 'Nothing to add today.',
        'kb_match': 'found',
    }
)

# === Helpers ===


def english() -> KnowledgeBase:
    """Load the English example."""
    return asyncio.run(load_knowledge_base(KB / 'example-en.yaml'))


class StubClient(FakeModelClient):
    """Client built from settings."""

    @classmethod
    def from_settings(cls, settings: object, transport: object = None) -> 'StubClient':
        """Ignore the settings given."""
        return cls([REPLY])

    async def aclose(self) -> None:
        """Accept the shutdown."""


# === Settings ===


def test_kb_is_loaded_from_settings_when_client_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)

    with TestClient(create_app(client=FakeModelClient([REPLY]))) as client:
        response = client.post('/api/suggest', json={'message': MESSAGE})

    assert response.status_code == 200
    assert response.json()['customer_reply'].endswith(DISCLAIMER)


def test_client_is_built_from_settings_when_kb_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr('reply_assistant.app.OpenAICompatibleClient', StubClient)

    with TestClient(create_app(kb=english())) as client:
        response = client.post('/api/suggest', json={'message': MESSAGE})

    assert response.status_code == 200
    assert response.json()['usage']['provider'] == 'fake'


def test_settings_are_not_read_when_kb_and_client_are_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def refuse() -> object:
        """Refuse a settings read."""
        raise AssertionError('Settings was read')

    monkeypatch.setattr('reply_assistant.app.Settings', refuse)

    app = create_app(kb=english(), client=FakeModelClient([REPLY]))

    with TestClient(app) as client:
        response = client.post('/api/suggest', json={'message': MESSAGE})

    assert response.status_code == 200
    assert response.json()['kb_match'] == 'found'

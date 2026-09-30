"""Application factory tests."""

import asyncio
import json
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from reply_assistant.model_client import OpenAICompatibleClient
from reply_assistant.settings import Settings
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
PROVIDER_REPLY = {
    'choices': [{'message': {'content': REPLY}}],
    'usage': {'prompt_tokens': 10, 'completion_tokens': 5},
}

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


def provider_answer(request: httpx2.Request) -> httpx2.Response:
    """Return one scripted reply."""
    return httpx2.Response(200, json=PROVIDER_REPLY)


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


# === Restart ===


async def test_second_lifespan_builds_a_fresh_owned_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    builds: list[OpenAICompatibleClient] = []
    build = OpenAICompatibleClient.from_settings

    def from_settings(settings: Settings) -> OpenAICompatibleClient:
        """Build the local client."""
        built = build(settings, transport=httpx2.MockTransport(provider_answer))
        builds.append(built)
        return built

    monkeypatch.setattr(OpenAICompatibleClient, 'from_settings', from_settings)
    kb = await load_knowledge_base(KB / 'example-en.yaml')
    app = create_app(kb=kb)
    codes = []

    for _ in range(2):
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app, raise_app_exceptions=False),
                base_url='http://app.test',
            ) as web,
        ):
            response = await web.post('/api/suggest', json={'message': MESSAGE})
            codes.append(response.status_code)

    assert codes == [200, 200]
    assert len(builds) == 2


# === Contract ===


def test_openapi_publishes_the_typed_usage_schema() -> None:
    app = create_app(kb=english(), client=FakeModelClient([REPLY]))

    spec = app.openapi()
    response = spec['paths']['/api/suggest']['post']['responses']['200']
    body = response['content']['application/json']['schema']

    assert body == {'$ref': '#/components/schemas/Suggestion'}
    assert spec['components']['schemas']['UsageReport'] == {
        'properties': {
            'input_tokens': {'title': 'Input Tokens', 'type': 'integer'},
            'output_tokens': {'title': 'Output Tokens', 'type': 'integer'},
            'provider': {'title': 'Provider', 'type': 'string'},
            'attempts': {'title': 'Attempts', 'type': 'integer'},
            'fallbacks': {
                'items': {'$ref': '#/components/schemas/FallbackSwitch'},
                'title': 'Fallbacks',
                'type': 'array',
            },
        },
        'required': ['input_tokens', 'output_tokens', 'provider', 'attempts'],
        'title': 'UsageReport',
        'description': 'Tokens of one suggestion.',
        'type': 'object',
    }

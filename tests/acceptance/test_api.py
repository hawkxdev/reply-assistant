"""Acceptance for issue 26."""

import asyncio
import importlib
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reply_assistant.knowledge_base import (
    KnowledgeBase,
    KnowledgeBaseError,
    load_knowledge_base,
)
from reply_assistant.model_client import ProviderError
from tests.acceptance.fakes import FakeModelClient

pytestmark = pytest.mark.xfail(strict=True, reason='issue 26 is not implemented')

# === Data ===

KB = Path(__file__).parents[2] / 'kb'
MESSAGE = 'Do you ship the powder to Minsk?'
VALID = {
    'customer_reply': 'Yes, we ship the powder to Minsk.',
    'upsell_product_id': 'measuring-spoon',
    'upsell_hint': 'Offer the spoon that measures one serving.',
    'kb_match': 'found',
}
CLAIM = json.dumps({**VALID, 'customer_reply': 'This powder cures allergies.'})
UPSTREAM = 'upstream detail 5d0e'
CLOSED_PORT = 'http://127.0.0.1:9/v1'
ENV = {
    'REPLY_ASSISTANT_PROVIDER_API_KEY': 'test-key',
    'REPLY_ASSISTANT_PROVIDER_BASE_URL': 'https://llm.example.test/v1',
    'REPLY_ASSISTANT_PROVIDER_MODEL': 'test-model',
}

# === Helpers ===


def english() -> KnowledgeBase:
    """Load the English example."""
    return asyncio.run(load_knowledge_base(KB / 'example-en.yaml'))


def api(fake: FakeModelClient | None = None) -> TestClient:
    """Build the application client."""
    create_app = importlib.import_module('reply_assistant.app').create_app
    if fake is None:
        return TestClient(create_app())
    return TestClient(create_app(kb=english(), client=fake))


def settings_env(monkeypatch: pytest.MonkeyPatch, kb_path: Path) -> None:
    """Set the settings environment."""
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv('REPLY_ASSISTANT_KB_PATH', str(kb_path))


# === Suggest ===


def test_suggest_returns_the_suggestion() -> None:
    fake = FakeModelClient([json.dumps(VALID)])

    with api(fake) as client:
        response = client.post('/api/suggest', json={'message': MESSAGE})

    assert response.status_code == 200
    assert response.json() == {
        'customer_reply': 'Yes, we ship the powder to Minsk.\n\n'
        'This product is a food supplement and is not a medicine.',
        'upsell_product_id': 'measuring-spoon',
        'upsell_hint': 'Offer the spoon that measures one serving.',
        'kb_match': 'found',
        'checks': {'rejected': [], 'disclaimer_appended': True},
        'usage': {
            'input_tokens': 100,
            'output_tokens': 20,
            'provider': 'fake',
            'attempts': 1,
        },
    }


# === Errors ===


def test_invalid_message_is_a_json_error() -> None:
    with api(FakeModelClient([])) as client:
        response = client.post('/api/suggest', json={'message': 'x' * 2001})

    assert response.status_code == 422
    assert set(response.json()) == {'code', 'message'}
    assert response.json()['code'] == 'invalid_request'


def test_rejected_suggestion_is_a_json_error() -> None:
    with api(FakeModelClient([CLAIM, CLAIM])) as client:
        response = client.post('/api/suggest', json={'message': MESSAGE})

    assert response.status_code == 502
    assert response.json()['code'] == 'suggestion_rejected'
    assert 'no_forbidden_claim' in response.json()['message']


@pytest.mark.parametrize(
    ('kind', 'status', 'code'),
    [('timeout', 504, 'provider_timeout'), ('server', 502, 'provider_error')],
    ids=['timeout', 'server'],
)
def test_provider_error_is_a_json_error(kind: str, status: int, code: str) -> None:
    fake = FakeModelClient(
        [ProviderError(provider='fake', kind=kind, message=UPSTREAM)]
    )

    with api(fake) as client:
        response = client.post('/api/suggest', json={'message': MESSAGE})

    assert response.status_code == status
    assert response.json()['code'] == code
    assert UPSTREAM not in response.text


# === Start ===


def test_service_starts_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings_env(monkeypatch, KB / 'example-en.yaml')
    monkeypatch.setenv('REPLY_ASSISTANT_PROVIDER_BASE_URL', CLOSED_PORT)

    with api() as client:
        response = client.post('/api/suggest', json={'message': MESSAGE})

    assert response.status_code == 502
    assert response.json()['code'] == 'provider_error'


def test_invalid_knowledge_base_stops_the_service(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    broken = tmp_path / 'kb.yaml'
    broken.write_text('company: Example\n', encoding='utf-8')
    settings_env(monkeypatch, broken)

    with pytest.raises(KnowledgeBaseError) as caught, api():
        pass

    assert caught.value.field == 'products'

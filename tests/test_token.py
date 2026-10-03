"""Token gate unit tests."""

import json
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from tests.acceptance.fakes import FakeModelClient

# === Data ===

KB = Path(__file__).parents[1] / 'kb'
REPLY = json.dumps(
    {
        'customer_reply': 'Yes, we ship the powder to Minsk.',
        'upsell_product_id': None,
        'upsell_hint': 'Nothing to add today.',
        'kb_match': 'found',
    }
)
MESSAGE = {'message': 'Do you ship the powder to Minsk?'}

# === Helpers ===


def token_env(monkeypatch: pytest.MonkeyPatch, token: str) -> None:
    """Set the token environment."""
    monkeypatch.setenv('REPLY_ASSISTANT_PROVIDER_API_KEY', 'test-key')
    monkeypatch.setenv(
        'REPLY_ASSISTANT_PROVIDER_BASE_URL', 'https://llm.example.test/v1'
    )
    monkeypatch.setenv('REPLY_ASSISTANT_PROVIDER_MODEL', 'test-model')
    monkeypatch.setenv('REPLY_ASSISTANT_KB_PATH', str(KB / 'example-en.yaml'))
    monkeypatch.setenv('REPLY_ASSISTANT_API_TOKEN', token)


# === Tests ===


def test_wrong_token_answers_the_unauthorized_envelope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token_env(monkeypatch, 'secret-token')

    with TestClient(create_app(client=FakeModelClient([REPLY]))) as client:
        response = client.post(
            '/api/suggest', headers={'X-API-Token': 'wrong'}, json=MESSAGE
        )

    assert response.status_code == 401
    assert response.json() == {
        'code': 'unauthorized',
        'message': 'the API token is missing or wrong',
    }


def test_token_comparison_is_constant_time(monkeypatch: pytest.MonkeyPatch) -> None:
    token_env(monkeypatch, 'secret-token')
    compared: list[tuple[bytes, bytes]] = []
    real = secrets.compare_digest

    def recording(left: bytes, right: bytes) -> bool:
        """Record one comparison."""
        compared.append((left, right))
        return real(left, right)

    monkeypatch.setattr(secrets, 'compare_digest', recording)

    with TestClient(create_app(client=FakeModelClient([REPLY]))) as client:
        response = client.post(
            '/api/suggest', headers={'X-API-Token': 'secret-token'}, json=MESSAGE
        )

    assert response.status_code == 200
    assert compared == [(b'secret-token', b'secret-token')]

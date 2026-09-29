"""Acceptance for issue 34."""

import importlib
import json
from pathlib import Path
from typing import Any

import httpx2
import pytest

from reply_assistant.app import create_app
from reply_assistant.settings import Settings

# === Data ===

KB_FILE = Path(__file__).parents[2] / 'kb' / 'example-en.yaml'
ENV = {
    'REPLY_ASSISTANT_PROVIDER_API_KEY': 'test-key',
    'REPLY_ASSISTANT_PROVIDER_BASE_URL': 'https://llm.example.test/v1',
    'REPLY_ASSISTANT_PROVIDER_MODEL': 'test-model',
    'REPLY_ASSISTANT_KB_PATH': str(KB_FILE),
}
PROVIDER_REPLY = {
    'choices': [
        {
            'message': {
                'content': json.dumps(
                    {
                        'customer_reply': 'Zeolite Powder costs 18.00 USD.',
                        'upsell_product_id': None,
                        'upsell_hint': '',
                        'kb_match': 'found',
                    }
                )
            }
        }
    ],
    'usage': {'prompt_tokens': 100, 'completion_tokens': 20},
}

# === Helpers ===


class TrackingTransport(httpx2.MockTransport):
    """Record transport shutdown calls."""

    def __init__(self) -> None:
        """Keep the shutdown count."""
        super().__init__(self.answer)
        self.closes = 0

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        """Return a provider reply."""
        return httpx2.Response(200, json=PROVIDER_REPLY)

    async def aclose(self) -> None:
        """Record the awaited shutdown."""
        self.closes += 1
        await super().aclose()


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TrackingTransport:
    """Route settings clients locally."""
    monkeypatch.chdir(tmp_path)
    for key, value in ENV.items():
        monkeypatch.setenv(key, value)
    module = importlib.import_module('reply_assistant.model_client')
    build = module.OpenAICompatibleClient.from_settings
    recorder = TrackingTransport()

    def from_settings(settings: Settings) -> Any:
        """Build the local client."""
        return build(settings, transport=recorder)

    monkeypatch.setattr(module.OpenAICompatibleClient, 'from_settings', from_settings)
    return recorder


# === Ownership ===


async def test_owned_client_closes_after_normal_shutdown(
    transport: TrackingTransport,
) -> None:
    app = create_app()

    async with app.router.lifespan_context(app):
        async with httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url='http://app.test'
        ) as web:
            response = await web.post('/api/suggest', json={'message': 'Price?'})
        assert response.status_code == 200
        assert transport.closes == 0

    assert transport.closes == 1


async def test_owned_client_closes_after_exceptional_shutdown(
    transport: TrackingTransport,
) -> None:
    app = create_app()

    with pytest.raises(RuntimeError, match='lifespan probe'):
        async with app.router.lifespan_context(app):
            raise RuntimeError('lifespan probe')

    assert transport.closes == 1


async def test_injected_client_stays_open_until_its_owner_closes_it(
    transport: TrackingTransport,
) -> None:
    module = importlib.import_module('reply_assistant.model_client')
    model = module.OpenAICompatibleClient.from_settings(Settings())
    app = create_app(client=model)

    try:
        async with app.router.lifespan_context(app):
            async with httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url='http://app.test'
            ) as web:
                response = await web.post('/api/suggest', json={'message': 'Price?'})
            assert response.status_code == 200
        assert transport.closes == 0
    finally:
        await model.aclose()

    assert transport.closes == 1

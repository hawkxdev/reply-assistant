"""Acceptance for issue 46."""

import importlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx2
import pytest
from pydantic import ValidationError

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import load_knowledge_base
from reply_assistant.model_client import Completion, ProviderError, Usage
from reply_assistant.service import SuggestionRejectedError, suggest
from reply_assistant.settings import Settings
from reply_assistant.suggestion import SuggestionRequest

pytestmark = pytest.mark.xfail(strict=True, reason='issue 46 is not implemented')

# === Data ===

KB_FILE = Path(__file__).parents[2] / 'kb' / 'example-en.yaml'
MESSAGES = [{'role': 'user', 'content': 'Price?'}]
SCHEMA = {'type': 'object', 'properties': {'answer': {'type': 'string'}}}
HIDDEN = 'private-upstream-text-46'
VALID = json.dumps(
    {
        'customer_reply': 'Zeolite Powder costs 18.00 USD.',
        'upsell_product_id': None,
        'upsell_hint': '',
        'kb_match': 'found',
    }
)
CLAIM = json.dumps(
    {
        'customer_reply': 'The powder cures allergies.',
        'upsell_product_id': None,
        'upsell_hint': '',
        'kb_match': 'partial',
    }
)
PRIMARY: dict[str, Any] = {
    'provider_api_key': 'test-key',
    'provider_base_url': 'https://primary.test/v1',
    'provider_model': 'primary-model',
    'kb_path': KB_FILE,
}
SECONDARY: dict[str, Any] = {
    'fallback_provider_api_key': 'secondary-test-key',
    'fallback_provider_base_url': 'https://secondary.test/v1',
    'fallback_provider_model': 'secondary-model',
}
PROVIDER_REPLY = {
    'choices': [{'message': {'content': VALID}}],
    'usage': {'prompt_tokens': 15, 'completion_tokens': 4},
}

# === Helpers ===


def fallback_class() -> Any:
    """Find the fallback client."""
    return importlib.import_module('reply_assistant.model_client').FallbackClient


def reply(
    provider: str,
    text: str = VALID,
    input_tokens: int = 12,
    output_tokens: int = 3,
) -> Completion:
    """Build one scripted completion."""
    return Completion(text, Usage(input_tokens, output_tokens, provider))


class ScriptedClient:
    """Record calls and shutdown."""

    def __init__(
        self,
        replies: list[Completion | Exception],
        close_error: Exception | None = None,
    ) -> None:
        """Keep the scripted outcomes."""
        self.replies = list(replies)
        self.close_error = close_error
        self.calls: list[tuple[list[dict[str, str]], dict[str, Any]]] = []
        self.closes = 0

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return the next outcome."""
        self.calls.append((messages, schema))
        outcome = self.replies.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    async def aclose(self) -> None:
        """Record one client shutdown."""
        self.closes += 1
        if self.close_error is not None:
            raise self.close_error


class TrackingTransport(httpx2.MockTransport):
    """Record provider transport calls."""

    def __init__(self, response: httpx2.Response) -> None:
        """Keep the local response."""
        self.response = response
        self.seen: list[httpx2.Request] = []
        self.closes = 0
        super().__init__(self.answer)

    def answer(self, request: httpx2.Request) -> httpx2.Response:
        """Return the local response."""
        self.seen.append(request)
        return self.response

    async def aclose(self) -> None:
        """Record the transport shutdown."""
        self.closes += 1
        await super().aclose()


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Isolate fallback environment sources."""
    monkeypatch.chdir(tmp_path)
    for name in (*SECONDARY, 'fallback_provider_json_mode'):
        monkeypatch.delenv('REPLY_ASSISTANT_' + name.upper(), raising=False)


# === Routing ===


@pytest.mark.parametrize('kind', ['timeout', 'connection', 'rate_limit', 'server'])
async def test_recoverable_failure_uses_secondary_once(
    kind: str, caplog: pytest.LogCaptureFixture
) -> None:
    primary = ScriptedClient([ProviderError('primary.test', kind, HIDDEN)])
    secondary = ScriptedClient([reply('secondary.test', input_tokens=15)])
    model = fallback_class()(primary=primary, secondary=secondary)
    caplog.set_level(logging.WARNING, logger='reply_assistant.model_client')

    result = await model.complete(MESSAGES, SCHEMA)

    assert result.text == VALID
    assert result.usage.provider == 'secondary.test'
    assert result.usage.input_tokens == 15
    assert result.usage.output_tokens == 3
    assert result.usage.fallback_from == 'primary.test'
    assert primary.calls == [(MESSAGES, SCHEMA)]
    assert secondary.calls == [(MESSAGES, SCHEMA)]
    assert [record.getMessage() for record in caplog.records] == [
        f'Fallback from primary.test after {kind}'
    ]
    assert HIDDEN not in caplog.text


async def test_primary_success_does_not_call_secondary() -> None:
    primary = ScriptedClient([reply('primary.test')])
    secondary = ScriptedClient([])
    model = fallback_class()(primary=primary, secondary=secondary)

    result = await model.complete(MESSAGES, SCHEMA)

    assert result.text == VALID
    assert result.usage.provider == 'primary.test'
    assert result.usage.input_tokens == 12
    assert result.usage.output_tokens == 3
    assert result.usage.fallback_from is None
    assert len(primary.calls) == 1
    assert secondary.calls == []


@pytest.mark.parametrize('kind', ['request', 'response'])
async def test_nonrecoverable_failure_does_not_call_secondary(kind: str) -> None:
    failure = ProviderError('primary.test', kind, HIDDEN)
    primary = ScriptedClient([failure])
    secondary = ScriptedClient([])
    model = fallback_class()(primary=primary, secondary=secondary)

    with pytest.raises(ProviderError, match=HIDDEN) as caught:
        await model.complete(MESSAGES, SCHEMA)

    assert caught.value is failure
    assert len(primary.calls) == 1
    assert secondary.calls == []


async def test_unexpected_failure_does_not_call_secondary() -> None:
    primary = ScriptedClient([ValueError(HIDDEN)])
    secondary = ScriptedClient([])
    model = fallback_class()(primary=primary, secondary=secondary)

    with pytest.raises(ValueError, match=HIDDEN):
        await model.complete(MESSAGES, SCHEMA)

    assert secondary.calls == []


async def test_secondary_failure_propagates_without_a_loop() -> None:
    failure = ProviderError('secondary.test', 'timeout', HIDDEN)
    primary = ScriptedClient([ProviderError('primary.test', 'server', HIDDEN)])
    secondary = ScriptedClient([failure])
    model = fallback_class()(primary=primary, secondary=secondary)

    with pytest.raises(ProviderError, match=HIDDEN) as caught:
        await model.complete(
            [{'role': 'user', 'content': 'Price and delivery?'}], SCHEMA
        )

    assert caught.value is failure
    assert len(primary.calls) == 1
    assert len(secondary.calls) == 1


# === Validation and reporting ===


async def test_model_rejection_retries_primary_without_a_switch() -> None:
    kb = await load_knowledge_base(KB_FILE)
    primary = ScriptedClient(
        [reply('primary.test', CLAIM), reply('primary.test', CLAIM)]
    )
    secondary = ScriptedClient([])
    model = fallback_class()(primary=primary, secondary=secondary)

    with pytest.raises(SuggestionRejectedError, match='no_forbidden_claim'):
        await suggest(SuggestionRequest(message='Price?'), kb, model)

    assert len(primary.calls) == 2
    assert secondary.calls == []


async def test_switch_history_survives_a_retry_answered_by_primary() -> None:
    kb = await load_knowledge_base(KB_FILE)
    primary = ScriptedClient(
        [ProviderError('primary.test', 'timeout', HIDDEN), reply('primary.test')]
    )
    secondary = ScriptedClient([reply('secondary.test', CLAIM, 17, 2)])
    model = fallback_class()(primary=primary, secondary=secondary)

    result = await suggest(SuggestionRequest(message='Price?'), kb, model)

    assert result.usage.provider == 'primary.test'
    assert result.usage.input_tokens == 29
    assert result.usage.output_tokens == 5
    assert result.usage.attempts == 2
    assert result.usage.model_dump()['fallbacks'] == [
        {'primary': 'primary.test', 'secondary': 'secondary.test'}
    ]
    assert result.checks.rejected == ['no_forbidden_claim']
    assert len(primary.calls) == 2
    assert len(secondary.calls) == 1


# === Configuration ===


@pytest.mark.parametrize(
    'names',
    [
        ('fallback_provider_api_key',),
        ('fallback_provider_base_url',),
        ('fallback_provider_model',),
        ('fallback_provider_api_key', 'fallback_provider_base_url'),
        ('fallback_provider_api_key', 'fallback_provider_model'),
        ('fallback_provider_base_url', 'fallback_provider_model'),
    ],
    ids=['key', 'url', 'model', 'key url', 'key model', 'url model'],
)
def test_partial_fallback_configuration_is_rejected_without_values(
    names: tuple[str, ...],
) -> None:
    partial = {name: SECONDARY[name] for name in names}

    with pytest.raises(ValidationError) as caught:
        Settings(**PRIMARY, **partial)

    assert 'test-key' not in str(caught.value)
    assert 'secondary.test' not in str(caught.value)
    assert 'secondary-model' not in str(caught.value)


@pytest.mark.parametrize(
    'json_mode', [True, False], ids=['default json', 'strict schema']
)
async def test_settings_factory_builds_the_secondary_with_its_own_configuration(
    json_mode: bool,
) -> None:
    options: dict[str, Any] = (
        {} if json_mode else {'fallback_provider_json_mode': False}
    )
    settings = Settings(**PRIMARY, **SECONDARY, **options)
    primary = TrackingTransport(httpx2.Response(429, json={'detail': HIDDEN}))
    secondary = TrackingTransport(httpx2.Response(200, json=PROVIDER_REPLY))
    model = fallback_class().from_settings(
        settings, primary_transport=primary, secondary_transport=secondary
    )

    try:
        result = await model.complete(
            [{'role': 'system', 'content': 'Use JSON.'}, *MESSAGES], SCHEMA
        )
    finally:
        await model.aclose()

    assert result.usage.provider == 'secondary.test'
    assert str(primary.seen[0].url) == 'https://primary.test/v1/chat/completions'
    assert str(secondary.seen[0].url) == 'https://secondary.test/v1/chat/completions'
    assert secondary.seen[0].headers['authorization'] == 'Bearer secondary-test-key'
    assert (
        json.loads(primary.seen[0].content)['response_format']['type'] == 'json_schema'
    )
    payload = json.loads(secondary.seen[0].content)
    assert payload['model'] == 'secondary-model'
    if json_mode:
        assert payload['response_format'] == {'type': 'json_object'}
        assert payload['messages'][-1]['role'] == 'system'
        assert 'JSON schema' in payload['messages'][-1]['content']
    else:
        assert payload['response_format']['type'] == 'json_schema'


# === Ownership and startup ===


def test_settings_factory_refuses_an_unconfigured_secondary() -> None:
    cls = fallback_class()

    with pytest.raises(ValueError, match='fallback') as caught:
        cls.from_settings(Settings(**PRIMARY))

    assert str(caught.value) == 'fallback provider is not configured'


async def test_configured_application_uses_and_rebuilds_owned_fallback_clients(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name, value in {**PRIMARY, **SECONDARY}.items():
        monkeypatch.setenv('REPLY_ASSISTANT_' + name.upper(), str(value))
    cls = fallback_class()
    build = cls.from_settings
    pairs: list[tuple[TrackingTransport, TrackingTransport]] = []
    client_class = httpx2.AsyncClient

    def refuse_network(request: httpx2.Request) -> httpx2.Response:
        """Reject an unexpected transport."""
        raise AssertionError('an unconfigured transport was used')

    def local_client(**kwargs: Any) -> httpx2.AsyncClient:
        """Replace missing transport locally."""
        if kwargs.get('transport') is None:
            kwargs['transport'] = httpx2.MockTransport(refuse_network)
        return client_class(**kwargs)

    monkeypatch.setattr(httpx2, 'AsyncClient', local_client)

    def from_settings(settings: Settings) -> Any:
        """Build two local providers."""
        primary = TrackingTransport(httpx2.Response(503, json={'detail': HIDDEN}))
        secondary = TrackingTransport(httpx2.Response(200, json=PROVIDER_REPLY))
        pairs.append((primary, secondary))
        return build(settings, primary_transport=primary, secondary_transport=secondary)

    monkeypatch.setattr(cls, 'from_settings', from_settings)
    app = create_app()
    for _ in range(2):
        async with (
            app.router.lifespan_context(app),
            httpx2.AsyncClient(
                transport=httpx2.ASGITransport(app=app), base_url='http://app.test'
            ) as web,
        ):
            response = await web.post('/api/suggest', json={'message': 'Price?'})
            assert response.status_code == 200
            assert response.json()['usage']['fallbacks'] == [
                {'primary': 'primary.test', 'secondary': 'secondary.test'}
            ]

    assert len(pairs) == 2
    assert [(primary.closes, secondary.closes) for primary, secondary in pairs] == [
        (1, 1),
        (1, 1),
    ]


async def test_injected_wrapper_is_closed_only_by_its_owner() -> None:
    kb = await load_knowledge_base(KB_FILE)
    primary = ScriptedClient([reply('primary.test')])
    secondary = ScriptedClient([])
    model = fallback_class()(primary=primary, secondary=secondary)
    app = create_app(kb=kb, client=model)

    try:
        async with app.router.lifespan_context(app):
            pass
        assert primary.closes == 0
        assert secondary.closes == 0
    finally:
        await model.aclose()

    assert primary.closes == 1
    assert secondary.closes == 1


async def test_secondary_closes_even_when_primary_close_fails() -> None:
    primary = ScriptedClient([], close_error=RuntimeError('close probe'))
    secondary = ScriptedClient([])
    model = fallback_class()(primary=primary, secondary=secondary)

    with pytest.raises(RuntimeError, match='close probe'):
        await model.aclose()

    assert secondary.closes == 1

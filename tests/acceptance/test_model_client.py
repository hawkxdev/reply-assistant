"""Acceptance for issue 22."""

import importlib
import json
from collections.abc import Callable
from types import ModuleType
from typing import Any

import httpx2
import pytest
from pydantic import SecretStr

pytestmark = pytest.mark.xfail(strict=True, reason='issue 22 is not implemented')

# === Data ===

BASE_URL = 'https://llm.example.test/v1'
KEY = 'test-key-7f3a'
MODEL = 'test-model'
MESSAGES = [
    {'role': 'system', 'content': 'You help the manager.'},
    {'role': 'user', 'content': 'Do you ship to Minsk?'},
]
SCHEMA = {'type': 'object', 'properties': {}, 'additionalProperties': False}
CONTENT = '{"customer_reply": "Yes."}'
REPLY = {
    'choices': [{'message': {'role': 'assistant', 'content': CONTENT}}],
    'usage': {'prompt_tokens': 120, 'completion_tokens': 40},
}
UPSTREAM_DETAIL = 'upstream detail 91c2'
JSON_MODE_RULE = (
    'Answer with one JSON object that follows this JSON schema: '
    '{"type": "object", "properties": {"kb_match": {"type": "string", '
    '"enum": ["found", "none"]}}, "required": ["kb_match"], '
    '"additionalProperties": false}'
)

Handler = Callable[[httpx2.Request], httpx2.Response]

# === Fixtures and helpers ===


@pytest.fixture
def module() -> ModuleType:
    """Import the client module."""
    return importlib.import_module('reply_assistant.model_client')


def strict_messages() -> list[dict[str, str]]:
    """Strict case messages."""
    return [
        {'role': 'system', 'content': 'Knowledge base A.'},
        {'role': 'user', 'content': 'Is the spoon made of steel?'},
    ]


def strict_schema() -> dict[str, Any]:
    """Strict case schema."""
    return {
        'type': 'object',
        'properties': {
            'upsell_product_id': {
                'anyOf': [
                    {'type': 'string', 'enum': ['spoon-5g', 'box-7']},
                    {'type': 'null'},
                ]
            }
        },
        'required': ['upsell_product_id'],
        'additionalProperties': False,
    }


def json_messages() -> list[dict[str, str]]:
    """JSON mode messages."""
    return [
        {'role': 'system', 'content': 'Knowledge base B.'},
        {'role': 'user', 'content': 'Do you ship to Brest?'},
    ]


def json_schema() -> dict[str, Any]:
    """JSON mode schema."""
    return {
        'type': 'object',
        'properties': {'kb_match': {'type': 'string', 'enum': ['found', 'none']}},
        'required': ['kb_match'],
        'additionalProperties': False,
    }


def recorder(
    response: httpx2.Response, seen: list[httpx2.Request]
) -> httpx2.MockTransport:
    """Record requests, answer once."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        """Keep the request."""
        seen.append(request)
        return response

    return httpx2.MockTransport(handle)


def failing(error: Exception) -> httpx2.MockTransport:
    """Raise a transport error."""

    def handle(request: httpx2.Request) -> httpx2.Response:
        """Raise the error."""
        raise error

    return httpx2.MockTransport(handle)


def client(
    module: ModuleType, transport: httpx2.MockTransport, url: str = BASE_URL
) -> Any:
    """Build the tested client."""
    return module.OpenAICompatibleClient(
        base_url=url, api_key=SecretStr(KEY), model=MODEL, transport=transport
    )


# === Request ===


async def test_request_goes_to_chat_completions(module: ModuleType) -> None:
    seen: list[httpx2.Request] = []
    transport = recorder(httpx2.Response(200, json=REPLY), seen)

    await client(module, transport, f'{BASE_URL}/').complete(MESSAGES, SCHEMA)

    assert len(seen) == 1
    assert seen[0].method == 'POST'
    assert str(seen[0].url) == 'https://llm.example.test/v1/chat/completions'
    assert seen[0].headers['authorization'] == f'Bearer {KEY}'


async def test_request_asks_for_strict_structured_output(module: ModuleType) -> None:
    seen: list[httpx2.Request] = []
    messages, schema = strict_messages(), strict_schema()

    await client(module, recorder(httpx2.Response(200, json=REPLY), seen)).complete(
        messages, schema
    )
    body = json.loads(seen[0].content)

    assert body['model'] == MODEL
    assert body['messages'] == strict_messages()
    assert body['response_format'] == {
        'type': 'json_schema',
        'json_schema': {
            'name': 'suggestion',
            'strict': True,
            'schema': strict_schema(),
        },
    }
    assert messages == strict_messages()
    assert schema == strict_schema()


async def test_json_mode_puts_the_schema_into_the_messages(
    module: ModuleType,
) -> None:
    seen: list[httpx2.Request] = []
    transport = recorder(httpx2.Response(200, json=REPLY), seen)
    messages, schema = json_messages(), json_schema()

    await module.OpenAICompatibleClient(
        base_url=BASE_URL,
        api_key=SecretStr(KEY),
        model=MODEL,
        transport=transport,
        json_mode=True,
    ).complete(messages, schema)
    body = json.loads(seen[0].content)

    assert body['model'] == MODEL
    assert body['response_format'] == {'type': 'json_object'}
    assert body['messages'] == [
        *json_messages(),
        {'role': 'system', 'content': JSON_MODE_RULE},
    ]
    assert messages == json_messages()
    assert schema == json_schema()


async def test_request_waits_long_enough_for_a_model(module: ModuleType) -> None:
    seen: list[httpx2.Request] = []

    await client(module, recorder(httpx2.Response(200, json=REPLY), seen)).complete(
        MESSAGES, SCHEMA
    )
    read = seen[0].extensions['timeout']['read']

    assert read is not None
    assert 30 <= read <= 120


async def test_client_is_built_from_settings(module: ModuleType) -> None:
    settings = importlib.import_module('reply_assistant.settings').Settings(
        provider_api_key=KEY,
        provider_base_url=BASE_URL,
        provider_model=MODEL,
        kb_path='kb/example-en.yaml',
    )
    seen: list[httpx2.Request] = []
    transport = recorder(httpx2.Response(200, json=REPLY), seen)

    await module.OpenAICompatibleClient.from_settings(
        settings, transport=transport
    ).complete(MESSAGES, SCHEMA)

    assert str(seen[0].url) == 'https://llm.example.test/v1/chat/completions'
    assert seen[0].headers['authorization'] == f'Bearer {KEY}'
    assert json.loads(seen[0].content)['model'] == MODEL


# === Response ===


async def test_reply_text_and_usage_are_returned(module: ModuleType) -> None:
    seen: list[httpx2.Request] = []

    completion = await client(
        module, recorder(httpx2.Response(200, json=REPLY), seen)
    ).complete(MESSAGES, SCHEMA)

    assert completion.text == CONTENT
    assert completion.usage.input_tokens == 120
    assert completion.usage.output_tokens == 40
    assert completion.usage.provider == 'llm.example.test'


async def test_zero_tokens_are_a_valid_count(module: ModuleType) -> None:
    reply = {**REPLY, 'usage': {'prompt_tokens': 0, 'completion_tokens': 0}}
    transport = recorder(httpx2.Response(200, json=reply), [])

    completion = await client(module, transport).complete(MESSAGES, SCHEMA)

    assert (completion.usage.input_tokens, completion.usage.output_tokens) == (0, 0)


# === Errors ===


@pytest.mark.parametrize(
    ('error', 'kind'),
    [
        (httpx2.ReadTimeout('slow'), 'timeout'),
        (httpx2.ConnectTimeout('slow'), 'timeout'),
        (httpx2.WriteTimeout('slow'), 'timeout'),
        (httpx2.PoolTimeout('slow'), 'timeout'),
        (httpx2.ConnectError('refused'), 'connection'),
    ],
    ids=[
        'read timeout',
        'connect timeout',
        'write timeout',
        'pool timeout',
        'connection',
    ],
)
async def test_transport_failure_is_a_provider_error(
    module: ModuleType, error: Exception, kind: str
) -> None:
    with pytest.raises(module.ProviderError) as caught:
        await client(module, failing(error)).complete(MESSAGES, SCHEMA)

    assert caught.value.kind == kind
    assert caught.value.provider == 'llm.example.test'


@pytest.mark.parametrize(
    ('status', 'kind'),
    [
        (429, 'rate_limit'),
        (500, 'server'),
        (503, 'server'),
        (400, 'request'),
        (401, 'request'),
    ],
)
async def test_error_status_is_a_provider_error(
    module: ModuleType, status: int, kind: str
) -> None:
    response = httpx2.Response(status, text=UPSTREAM_DETAIL)

    with pytest.raises(module.ProviderError) as caught:
        await client(module, recorder(response, [])).complete(MESSAGES, SCHEMA)

    assert caught.value.kind == kind
    assert UPSTREAM_DETAIL not in str(caught.value)


@pytest.mark.parametrize(
    'response',
    [
        httpx2.Response(200, text='not json'),
        httpx2.Response(200, json=[]),
        httpx2.Response(200, json={'usage': REPLY['usage']}),
        httpx2.Response(200, json={**REPLY, 'choices': []}),
        httpx2.Response(
            200, json={**REPLY, 'choices': [{'message': {'content': None}}]}
        ),
        httpx2.Response(200, json={**REPLY, 'choices': [{'message': {'content': 5}}]}),
        httpx2.Response(200, json={'choices': REPLY['choices']}),
        httpx2.Response(200, json={**REPLY, 'usage': {'completion_tokens': 40}}),
        httpx2.Response(200, json={**REPLY, 'usage': {'prompt_tokens': 120}}),
        httpx2.Response(
            200,
            json={**REPLY, 'usage': {'prompt_tokens': '120', 'completion_tokens': 40}},
        ),
        httpx2.Response(
            200,
            json={**REPLY, 'usage': {'prompt_tokens': 120, 'completion_tokens': -1}},
        ),
        httpx2.Response(
            200,
            json={**REPLY, 'usage': {'prompt_tokens': 120, 'completion_tokens': 1.5}},
        ),
        httpx2.Response(
            200,
            json={**REPLY, 'usage': {'prompt_tokens': 120, 'completion_tokens': True}},
        ),
    ],
    ids=[
        'not json',
        'not an object',
        'no choices',
        'empty choices',
        'null content',
        'number content',
        'no usage',
        'no prompt count',
        'no completion count',
        'text tokens',
        'negative tokens',
        'fraction tokens',
        'boolean tokens',
    ],
)
async def test_malformed_reply_is_a_provider_error(
    module: ModuleType, response: httpx2.Response
) -> None:
    with pytest.raises(module.ProviderError) as caught:
        await client(module, recorder(response, [])).complete(MESSAGES, SCHEMA)

    assert caught.value.kind == 'response'


async def test_error_never_shows_the_key(module: ModuleType) -> None:
    response = httpx2.Response(401, text=f'bad key {KEY}')

    with pytest.raises(module.ProviderError) as caught:
        await client(module, recorder(response, [])).complete(MESSAGES, SCHEMA)

    assert KEY not in str(caught.value)
    assert KEY not in repr(caught.value)

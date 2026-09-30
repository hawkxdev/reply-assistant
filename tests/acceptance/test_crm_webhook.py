"""Acceptance for issue 48."""

import asyncio
import importlib
import json
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx2
import pytest
from starlette.types import Message, Scope

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from reply_assistant.model_client import Completion, ModelClient, ProviderError, Usage
from reply_assistant.service import Suggestion, suggest
from reply_assistant.suggestion import SuggestionRequest

pytestmark = pytest.mark.xfail(strict=True, reason='issue 48 is not implemented')

# === Data ===

KB_FILE = Path(__file__).parents[2] / 'kb' / 'example-en.yaml'
URL = '/webhooks/crm/messages'
FORM = 'application/x-www-form-urlencoded'
BODY = b'message%5Badd%5D%5B0%5D%5Btext%5D=Price%3F&account%5Bid%5D=42'
HIDDEN = 'private-customer-detail-48'
DISCLAIMER = 'This product is a food supplement and is not a medicine.'
VALID = json.dumps(
    {
        'customer_reply': 'Zeolite Powder costs 18.00 USD.',
        'upsell_product_id': None,
        'upsell_hint': '',
        'kb_match': 'found',
    }
)
CLAIM = VALID.replace('Zeolite Powder costs 18.00 USD.', 'The powder cures allergies.')

# === Helpers ===


@pytest.fixture
async def kb() -> KnowledgeBase:
    """Load the example catalogue."""
    return await load_knowledge_base(KB_FILE)


def crm_module() -> Any:
    """Find the event parser."""
    return importlib.import_module('reply_assistant.crm_event')


class ScriptedClient:
    """Gate scripted model outcomes."""

    def __init__(self, replies: list[str | Exception], paused: bool = False) -> None:
        """Keep outcomes and gates."""
        self.replies = list(replies)
        self.entered = asyncio.Event()
        self.release = asyncio.Event()
        if not paused:
            self.release.set()
        self.calls: list[tuple[list[dict[str, str]], dict[str, Any]]] = []

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Return the gated outcome."""
        self.calls.append((messages, schema))
        self.entered.set()
        await self.release.wait()
        outcome = self.replies.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Completion(outcome, Usage(10, 3, 'fake'))


async def post(
    kb: KnowledgeBase, model: ScriptedClient, body: bytes, media_type: str = FORM
) -> httpx2.Response:
    """Post one local event."""
    app = create_app(kb=kb, client=model)
    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app, raise_app_exceptions=False),
        base_url='http://app.test',
    ) as web:
        return await web.post(URL, content=body, headers={'content-type': media_type})


# === Parsing ===


@pytest.mark.parametrize(
    ('body', 'expected'),
    [
        (b'message[add][0][text]=Hello+world%2B', 'Hello world+'),
        (
            b'message%5Badd%5D%5B0%5D%5Btext%5D=%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82',
            'Привет',
        ),
        (
            b'account[id]=42&message[add][0][text]=++Price%3F++&other=value',
            '  Price?  ',
        ),
    ],
    ids=['plus', 'unicode keys', 'untrimmed extra fields'],
)
def test_parser_preserves_decoded_customer_text(body: bytes, expected: str) -> None:
    assert crm_module().parse_crm_event(body) == expected


def test_parser_accepts_the_unicode_character_limit() -> None:
    body = ('message[add][0][text]=' + 'я' * 2000).encode()

    result = crm_module().parse_crm_event(body)

    assert len(result) == 2000
    assert set(result) == {'я'}


@pytest.mark.parametrize(
    'body',
    [
        b'account[id]=42',
        b'message[add][0][text]=',
        b'message[add][0][text]=one&message[add][0][text]=two',
        b'message[add][0][text]=one&message[add][1][text]=two',
        b'message[add][0][text]=bad%ZZ',
        b'message[add][0][text]=%FF',
        b'message[add][0][text]=\xff',
        b'message[add][0][text]=' + b'x' * 2001,
    ],
    ids=[
        'missing',
        'empty',
        'duplicate',
        'batch',
        'percent',
        'encoded utf8',
        'raw utf8',
        'long',
    ],
)
def test_parser_rejects_invalid_events_without_their_contents(body: bytes) -> None:
    module = crm_module()

    with pytest.raises(
        module.CRMEventError, match='invalid CRM message event'
    ) as caught:
        module.parse_crm_event(body + b'&private=' + HIDDEN.encode())

    assert HIDDEN not in str(caught.value)


# === Acknowledgement ===


async def test_acknowledgement_is_sent_before_the_model_completes(
    kb: KnowledgeBase,
) -> None:
    model = ScriptedClient([VALID], paused=True)
    app = create_app(kb=kb, client=model)
    sent: list[Message] = []
    ack = asyncio.Event()
    delivered = False

    async def receive() -> Message:
        """Deliver one request body."""
        nonlocal delivered
        if not delivered:
            delivered = True
            return {'type': 'http.request', 'body': BODY, 'more_body': False}
        await ack.wait()
        return {'type': 'http.disconnect'}

    async def send(message: Message) -> None:
        """Record the acknowledgement bytes."""
        sent.append(message)
        if message['type'] == 'http.response.body' and not message.get('more_body'):
            ack.set()

    scope: Scope = {
        'type': 'http',
        'asgi': {'version': '3.0', 'spec_version': '2.4'},
        'http_version': '1.1',
        'method': 'POST',
        'scheme': 'http',
        'path': URL,
        'raw_path': URL.encode(),
        'query_string': b'',
        'root_path': '',
        'headers': [(b'content-type', FORM.encode()), (b'host', b'app.test')],
        'client': ('127.0.0.1', 1234),
        'server': ('app.test', 80),
    }
    task = asyncio.create_task(app(scope, receive, send))
    try:
        await asyncio.wait_for(ack.wait(), timeout=1.5)
        assert sent[0]['status'] == 202
        assert json.loads(sent[-1]['body']) == {'accepted': True}
        await asyncio.wait_for(model.entered.wait(), timeout=1.5)
        assert not task.done()
    finally:
        model.release.set()
        await asyncio.wait_for(task, timeout=2)


async def test_valid_form_reaches_the_existing_checked_service(
    kb: KnowledgeBase, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    app_module = importlib.import_module('reply_assistant.app')
    service_module = importlib.import_module('reply_assistant.service')
    model = ScriptedClient([VALID])
    calls: list[tuple[str, KnowledgeBase, ModelClient]] = []
    results: list[Suggestion] = []

    async def checked(
        request: SuggestionRequest, catalogue: KnowledgeBase, client: ModelClient
    ) -> Suggestion:
        """Record the shared service."""
        calls.append((request.message, catalogue, client))
        result = await suggest(request, catalogue, client)
        results.append(result)
        return result

    monkeypatch.setattr(app_module, 'suggest', checked)
    monkeypatch.setattr(service_module, 'suggest', checked)
    caplog.set_level(logging.DEBUG, logger='reply_assistant.app')

    response = await post(kb, model, BODY, FORM + '; charset=utf-8')

    assert response.status_code == 202
    assert response.json() == {'accepted': True}
    assert calls == [('Price?', kb, model)]
    assert results[0].customer_reply.endswith(DISCLAIMER)
    assert 'CRM suggestion ready' in caplog.messages
    assert 'Price?' not in caplog.text
    assert 'Zeolite Powder costs' not in caplog.text


# === Rejection and bounded reads ===


@pytest.mark.parametrize(
    ('body', 'media_type', 'status', 'code'),
    [
        (b'private=' + HIDDEN.encode(), FORM, 422, 'invalid_crm_event'),
        (BODY, 'application/json', 415, 'http_error'),
        (b'x' * 65537, FORM, 413, 'http_error'),
    ],
    ids=['invalid event', 'media type', 'body size'],
)
async def test_invalid_request_never_calls_a_model(
    kb: KnowledgeBase, body: bytes, media_type: str, status: int, code: str
) -> None:
    model = ScriptedClient([])

    response = await post(kb, model, body, media_type)

    assert response.status_code == status
    data = response.json()
    assert set(data) == {'code', 'message'}
    assert data['code'] == code
    assert isinstance(data['message'], str)
    assert data['message']
    assert HIDDEN not in response.text
    assert model.calls == []


async def test_body_limit_stops_consuming_the_stream(kb: KnowledgeBase) -> None:
    model = ScriptedClient([])
    app = create_app(kb=kb, client=model)

    async def chunks() -> AsyncIterator[bytes]:
        """Expose an excessive stream."""
        yield b'x' * 32768
        yield b'x' * 32769
        raise AssertionError('the oversized body was consumed further')

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app, raise_app_exceptions=False),
        base_url='http://app.test',
    ) as web:
        response = await web.post(URL, content=chunks(), headers={'content-type': FORM})

    assert response.status_code == 413
    assert model.calls == []


# === Processing failures ===


@pytest.mark.parametrize(
    ('outcomes', 'code'),
    [
        ([ProviderError('fake', 'server', HIDDEN)], 'provider_error'),
        ([CLAIM, CLAIM], 'suggestion_rejected'),
        ([ValueError(HIDDEN)], 'internal_error'),
    ],
    ids=['provider', 'rejected reply', 'unexpected'],
)
async def test_processing_failure_keeps_the_ack_and_hides_details(
    kb: KnowledgeBase,
    outcomes: list[str | Exception],
    code: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = ScriptedClient(outcomes)
    caplog.set_level(logging.DEBUG, logger='reply_assistant.app')

    response = await post(kb, model, BODY)

    assert response.status_code == 202
    assert response.json() == {'accepted': True}
    assert f'CRM suggestion failed: {code}' in caplog.messages
    assert HIDDEN not in caplog.text
    assert 'cures allergies' not in caplog.text

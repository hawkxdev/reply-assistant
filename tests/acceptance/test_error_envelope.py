"""Acceptance for issue 35."""

from pathlib import Path
from typing import Any

import httpx2
import pytest

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import KnowledgeBase, load_knowledge_base
from reply_assistant.model_client import Completion
from tests.acceptance.fakes import FakeModelClient

# === Data ===

KB_FILE = Path(__file__).parents[2] / 'kb' / 'example-en.yaml'
INTERNAL_DETAIL = 'INTERNAL-ONLY-34CD'

# === Helpers ===


@pytest.fixture
async def kb() -> KnowledgeBase:
    """Load the example catalogue."""
    return await load_knowledge_base(KB_FILE)


class FailingClient:
    """Raise an unexpected failure."""

    def __init__(self, error: Exception) -> None:
        """Keep the injected failure."""
        self.error = error

    async def complete(
        self, messages: list[dict[str, str]], schema: dict[str, Any]
    ) -> Completion:
        """Raise the injected failure."""
        raise self.error


# === Framework errors ===


@pytest.mark.parametrize(
    ('method', 'path', 'status', 'code', 'allow', 'content'),
    [
        ('GET', '/missing-route', 404, 'not_found', None, None),
        ('POST', '/health', 405, 'method_not_allowed', 'GET', None),
        ('POST', '/api/suggest', 400, 'http_error', None, b'\xff'),
    ],
    ids=['not found', 'method not allowed', 'body parse failure'],
)
async def test_framework_errors_use_the_public_error_body(
    kb: KnowledgeBase,
    method: str,
    path: str,
    status: int,
    code: str,
    allow: str | None,
    content: bytes | None,
) -> None:
    app = create_app(kb=kb, client=FakeModelClient([]))

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app, raise_app_exceptions=False),
        base_url='http://app.test',
    ) as web:
        response = await web.request(
            method,
            path,
            content=content,
            headers={'content-type': 'application/json'}
            if content is not None
            else None,
        )

    assert response.status_code == status
    assert response.headers['content-type'].startswith('application/json')
    body = response.json()
    assert set(body) == {'code', 'message'}
    assert body['code'] == code
    assert isinstance(body['message'], str)
    assert body['message'].strip()
    if allow is not None:
        assert response.headers['allow'] == allow


# === Unexpected errors ===


@pytest.mark.parametrize(
    'error_type', [RuntimeError, ValueError], ids=['runtime', 'value']
)
async def test_unexpected_errors_hide_the_exception_text(
    kb: KnowledgeBase, error_type: type[Exception]
) -> None:
    app = create_app(kb=kb, client=FailingClient(error_type(INTERNAL_DETAIL)))

    async with httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app, raise_app_exceptions=False),
        base_url='http://app.test',
    ) as web:
        response = await web.post('/api/suggest', json={'message': 'Price?'})

    assert response.status_code == 500
    assert response.headers['content-type'].startswith('application/json')
    body = response.json()
    assert set(body) == {'code', 'message'}
    assert body['code'] == 'internal_error'
    assert isinstance(body['message'], str)
    assert body['message'].strip()
    assert 'internal-only-34cd' not in response.text.casefold()

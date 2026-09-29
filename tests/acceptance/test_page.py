"""Acceptance for issue 27."""

import asyncio
import importlib
import re
from pathlib import Path

import httpx2
import pytest
from fastapi.testclient import TestClient

from reply_assistant.knowledge_base import load_knowledge_base
from tests.acceptance.fakes import FakeModelClient

pytestmark = pytest.mark.xfail(strict=True, reason='issue 27 is not implemented')

# === Data ===

KB = Path(__file__).parents[2] / 'kb'
PARTS = [
    'deal',
    'chat',
    'assistant',
    'customer-input',
    'chat-input',
    'insert-reply',
    'reply',
    'hint',
    'checks',
    'usage',
    'mock-notice',
]
NOTICES = [
    'Mock of a CRM dialog window. Nothing is sent anywhere.',
    'Макет окна диалога CRM. Ничего никуда не отправляется.',
]
TRADEMARKS = ['amocrm', 'kommo', 'bitrix', 'битрикс']
EXTERNAL = re.compile(r'(?:src|href)\s*=\s*["\']?(?:https?:)?//|url\(\s*["\']?https?:')

# === Helpers ===


def get_page(name: str = 'example-en.yaml') -> httpx2.Response:
    """Fetch the page."""
    create_app = importlib.import_module('reply_assistant.app').create_app
    kb = asyncio.run(load_knowledge_base(KB / name))
    with TestClient(create_app(kb=kb, client=FakeModelClient([]))) as client:
        response = client.get('/')
    assert response.status_code == 200
    return response


# === Page ===


def test_page_is_html() -> None:
    response = get_page()

    assert response.headers['content-type'].startswith('text/html')


@pytest.mark.parametrize(
    ('name', 'language'),
    [('example-en.yaml', 'en'), ('example-ru.yaml', 'ru')],
    ids=['en', 'ru'],
)
def test_page_takes_the_language_of_the_base(name: str, language: str) -> None:
    found = re.search(r'<html lang="([a-z]+)"', get_page(name).text)

    assert found is not None
    assert found.group(1) == language


@pytest.mark.parametrize('part', PARTS)
def test_page_has_the_part(part: str) -> None:
    assert f'id="{part}"' in get_page().text


def test_page_states_it_is_a_mock_in_both_languages() -> None:
    text = get_page().text

    assert NOTICES[0] in text
    assert NOTICES[1] in text


def test_page_names_no_crm() -> None:
    text = get_page().text.lower()

    assert [mark for mark in TRADEMARKS if mark in text] == []


def test_page_loads_nothing_from_outside() -> None:
    assert EXTERNAL.search(get_page().text) is None


def test_page_asks_the_suggest_endpoint() -> None:
    assert '/api/suggest' in get_page().text

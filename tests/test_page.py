"""Web page route tests."""

import asyncio
from dataclasses import replace
from importlib.resources import files
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import load_knowledge_base
from tests.acceptance.fakes import FakeModelClient

# === Data ===

KB = Path(__file__).parents[1] / 'kb'

# === Page ===


def test_page_changes_only_the_language() -> None:
    kb = replace(
        asyncio.run(load_knowledge_base(KB / 'example-en.yaml')), language='de'
    )
    source = (
        files('reply_assistant')
        .joinpath('static', 'index.html')
        .read_text(encoding='utf-8')
    )

    with TestClient(create_app(kb=kb, client=FakeModelClient([]))) as client:
        response = client.get('/')

    assert response.status_code == 200
    assert response.text == source.replace('<html lang="en">', '<html lang="de">')


def test_page_fails_before_the_application_started() -> None:
    client = TestClient(create_app())

    with pytest.raises(RuntimeError):
        client.get('/')


def test_page_names_the_switch_in_both_languages() -> None:
    kb = asyncio.run(load_knowledge_base(KB / 'example-en.yaml'))

    with TestClient(create_app(kb=kb, client=FakeModelClient([]))) as client:
        response = client.get('/')

    assert response.status_code == 200
    assert 'Provider fallback' in response.text
    assert 'Переключение провайдера' in response.text

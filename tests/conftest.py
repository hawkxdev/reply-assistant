"""Shared test fixtures."""

import asyncio
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import load_knowledge_base
from tests.acceptance.fakes import FakeModelClient

KB = Path(__file__).parents[1] / 'kb'


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provide an application client."""
    kb = asyncio.run(load_knowledge_base(KB / 'example-en.yaml'))
    with TestClient(create_app(kb=kb, client=FakeModelClient([]))) as test_client:
        yield test_client

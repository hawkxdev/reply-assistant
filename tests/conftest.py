"""Shared test fixtures."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app


@pytest.fixture
def client() -> Iterator[TestClient]:
    """Provide an application client."""
    with TestClient(create_app()) as test_client:
        yield test_client

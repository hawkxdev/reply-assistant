"""Acceptance test for issue 3."""

import pytest
from fastapi.testclient import TestClient


@pytest.mark.xfail(strict=True, reason='issue 3 is not implemented')
def test_health_names_the_service(client: TestClient) -> None:
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json()['name'] == 'reply-assistant'
    assert response.json()['status'] == 'ok'

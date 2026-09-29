"""Acceptance test for issue 3."""

from fastapi.testclient import TestClient


def test_health_names_the_service(client: TestClient) -> None:
    response = client.get('/health')

    assert response.status_code == 200
    assert response.json()['name'] == 'reply-assistant'
    assert response.json()['status'] == 'ok'

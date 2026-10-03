"""Acceptance for the registry and the API token."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import KnowledgeBaseError
from tests.acceptance.fakes import FakeModelClient

KB = Path(__file__).parents[2] / 'kb'
PROVIDER = {
    'REPLY_ASSISTANT_PROVIDER_API_KEY': 'test-key',
    'REPLY_ASSISTANT_PROVIDER_BASE_URL': 'https://llm.example.test/v1',
    'REPLY_ASSISTANT_PROVIDER_MODEL': 'test-model',
}
EN_REPLY = json.dumps(
    {
        'customer_reply': 'Yes, we ship the powder to Minsk.',
        'upsell_product_id': 'measuring-spoon',
        'upsell_hint': 'Offer the spoon that measures one serving.',
        'kb_match': 'found',
    }
)
RU_REPLY = json.dumps(
    {
        'customer_reply': 'Эфиопия Сидамо, зерно, пачка 250 г, стоит 890 RUB.',
        'upsell_product_id': 'paper-filters-100',
        'upsell_hint': 'Предложите бумажные фильтры для воронки.',
        'kb_match': 'found',
    }
)

# === Fixtures and helpers ===


@pytest.fixture
def kb_directory(tmp_path: Path) -> Path:
    """Provide a directory with two valid bases."""
    bases = tmp_path / 'kb'
    bases.mkdir()
    for name in ('example-en.yaml', 'example-ru.yaml'):
        (bases / name).write_bytes((KB / name).read_bytes())
    return tmp_path


def write_registry(directory: Path, clients: dict[str, str]) -> Path:
    """Write one registry file."""
    registry: dict[str, str] = {'default': 'kb/example-en.yaml'}
    registry.update(clients)
    path = directory / 'registry.json'
    path.write_text(json.dumps(registry), encoding='utf-8')
    return path


def registry_env(monkeypatch: pytest.MonkeyPatch, registry: Path) -> None:
    """Point the settings at one registry."""
    for name, value in PROVIDER.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('REPLY_ASSISTANT_KB_PATH', raising=False)
    monkeypatch.setenv('REPLY_ASSISTANT_KB_REGISTRY', str(registry))


def prompt_of(fake: FakeModelClient) -> str:
    """Return the system prompt of the call."""
    return fake.calls[0][0][0]['content']


# === Registry selection ===


def test_registered_client_selects_own_base(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = write_registry(kb_directory, {'client-ru': 'kb/example-ru.yaml'})
    registry_env(monkeypatch, registry)
    fake = FakeModelClient([RU_REPLY])

    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest',
            headers={'X-Client-Id': 'client-ru'},
            json={'message': 'Сколько стоит Эфиопия Сидамо?'},
        )

    assert response.status_code == 200
    prompt = prompt_of(fake)
    assert 'Эфиопия Сидамо' in prompt
    assert '890 RUB' in prompt


def test_default_base_without_header(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = write_registry(kb_directory, {'client-ru': 'kb/example-ru.yaml'})
    registry_env(monkeypatch, registry)
    fake = FakeModelClient([EN_REPLY])

    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest', json={'message': 'Do you ship the powder to Minsk?'}
        )

    assert response.status_code == 200
    prompt = prompt_of(fake)
    assert 'Zeolite Powder' in prompt
    assert '18.00 USD' in prompt


def test_unknown_client_falls_back_to_default(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = write_registry(kb_directory, {'client-ru': 'kb/example-ru.yaml'})
    registry_env(monkeypatch, registry)
    fake = FakeModelClient([EN_REPLY])

    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest',
            headers={'X-Client-Id': 'ghost'},
            json={'message': 'Do you ship the powder to Minsk?'},
        )

    assert response.status_code == 200
    prompt = prompt_of(fake)
    assert 'Zeolite Powder' in prompt
    assert '18.00 USD' in prompt


def test_registry_is_re_read_per_request(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = write_registry(kb_directory, {'client-ru': 'kb/example-ru.yaml'})
    registry_env(monkeypatch, registry)
    fake = FakeModelClient([RU_REPLY, EN_REPLY])

    with TestClient(create_app(client=fake)) as client:
        before = client.post(
            '/api/suggest',
            headers={'X-Client-Id': 'client-ru'},
            json={'message': 'Сколько стоит Эфиопия Сидамо?'},
        )
        mapping = json.loads(registry.read_text(encoding='utf-8'))
        mapping['client-ru'] = 'kb/example-en.yaml'
        registry.write_text(json.dumps(mapping), encoding='utf-8')
        after = client.post(
            '/api/suggest',
            headers={'X-Client-Id': 'client-ru'},
            json={'message': 'Do you ship the powder to Minsk?'},
        )

    assert before.status_code == 200
    assert '890 RUB' in fake.calls[0][0][0]['content']
    assert after.status_code == 200
    assert '18.00 USD' in fake.calls[1][0][0]['content']


# === Validation ===


def test_invalid_base_is_refused_at_load(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    broken = kb_directory / 'kb' / 'broken.yaml'
    broken.write_text('company: Example\n', encoding='utf-8')
    registry = write_registry(kb_directory, {'broken': 'kb/broken.yaml'})
    registry_env(monkeypatch, registry)

    with pytest.raises(KnowledgeBaseError), TestClient(create_app()):
        pass


def test_traversal_path_is_rejected(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = write_registry(kb_directory, {'evil': '../../etc/passwd'})
    registry_env(monkeypatch, registry)

    with pytest.raises(Exception, match='traversal'), TestClient(create_app()):
        pass


# === Optional API token ===


def test_token_set_requires_the_header(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = write_registry(kb_directory, {})
    registry_env(monkeypatch, registry)
    monkeypatch.setenv('REPLY_ASSISTANT_API_TOKEN', 'secret-token')
    fake = FakeModelClient([EN_REPLY])

    with TestClient(create_app(client=fake)) as client:
        no_header = client.post('/api/suggest', json={'message': 'Hello'})
        wrong = client.post(
            '/api/suggest',
            headers={'X-API-Token': 'wrong'},
            json={'message': 'Hello'},
        )
        webhook = client.post(
            '/webhooks/crm/messages',
            data={'message[add][0][text]': 'Hello'},
        )
        right = client.post(
            '/api/suggest',
            headers={'X-API-Token': 'secret-token'},
            json={'message': 'Do you ship the powder to Minsk?'},
        )

    assert no_header.status_code == 401
    assert wrong.status_code == 401
    assert webhook.status_code == 401
    assert set(no_header.json()) == {'code', 'message'}
    assert right.status_code == 200


def test_token_unset_means_no_check(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    registry = write_registry(kb_directory, {})
    registry_env(monkeypatch, registry)
    monkeypatch.delenv('REPLY_ASSISTANT_API_TOKEN', raising=False)
    fake = FakeModelClient([EN_REPLY])

    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest', json={'message': 'Do you ship the powder to Minsk?'}
        )

    assert response.status_code == 200

"""Registry unit tests."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from reply_assistant.app import create_app
from reply_assistant.knowledge_base import KnowledgeBaseError
from reply_assistant.registry import RegistryError, load_registry
from tests.acceptance.fakes import FakeModelClient

# === Data ===

KB = Path(__file__).parents[1] / 'kb'
REPLY = json.dumps(
    {
        'customer_reply': 'Yes, we ship the powder to Minsk.',
        'upsell_product_id': None,
        'upsell_hint': 'Nothing to add today.',
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
PROVIDER = {
    'REPLY_ASSISTANT_PROVIDER_API_KEY': 'test-key',
    'REPLY_ASSISTANT_PROVIDER_BASE_URL': 'https://llm.example.test/v1',
    'REPLY_ASSISTANT_PROVIDER_MODEL': 'test-model',
}
SECOND = (
    'language: en\n'
    'reply_rules:\n'
    '  - Be kind.\n'
    'forbidden_claims:\n'
    '  - No claims.\n'
    'products:\n'
    '  - id: spoon\n'
    '    name: Spoon\n'
    '    form: tool\n'
    '    price: 1 USD\n'
    '    description: A spoon.\n'
)

# === Fixtures and helpers ===


@pytest.fixture
def kb_directory(tmp_path: Path) -> Path:
    """Provide a directory with bases."""
    bases = tmp_path / 'kb'
    bases.mkdir()
    for name in ('example-en.yaml', 'example-ru.yaml'):
        (bases / name).write_bytes((KB / name).read_bytes())
    return tmp_path


def write_registry(directory: Path, entries: dict[str, str]) -> Path:
    """Write one registry file."""
    path = directory / 'registry.json'
    path.write_text(json.dumps(entries), encoding='utf-8')
    return path


def registry_env(monkeypatch: pytest.MonkeyPatch, registry: Path) -> None:
    """Point the settings at one registry."""
    for name, value in PROVIDER.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv('REPLY_ASSISTANT_KB_PATH', raising=False)
    monkeypatch.delenv('REPLY_ASSISTANT_API_TOKEN', raising=False)
    monkeypatch.setenv('REPLY_ASSISTANT_KB_REGISTRY', str(registry))


# === Startup validation ===


@pytest.mark.parametrize(
    'content', ['{"default": "kb/example', '["default"]', '{"default": 5}']
)
async def test_registry_parse_error_is_rejected(tmp_path: Path, content: str) -> None:
    path = tmp_path / 'registry.json'
    path.write_text(content, encoding='utf-8')

    with pytest.raises(RegistryError):
        await load_registry(path)


async def test_registry_without_default_is_rejected(kb_directory: Path) -> None:
    path = write_registry(kb_directory, {'client-ru': 'kb/example-ru.yaml'})

    with pytest.raises(RegistryError, match='default'):
        await load_registry(path)


async def test_missing_registry_file_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(RegistryError):
        await load_registry(tmp_path / 'registry.json')


async def test_entries_are_validated_in_file_order(kb_directory: Path) -> None:
    (kb_directory / 'kb' / 'first.yaml').write_text(
        'company: First\n', encoding='utf-8'
    )
    (kb_directory / 'kb' / 'second.yaml').write_text(SECOND, encoding='utf-8')
    path = write_registry(
        kb_directory,
        {
            'default': 'kb/example-en.yaml',
            'first': 'kb/first.yaml',
            'second': 'kb/second.yaml',
        },
    )

    with pytest.raises(KnowledgeBaseError, match='products is missing'):
        await load_registry(path)


# === Per request re read ===


async def test_select_rejects_traversal_added_later(kb_directory: Path) -> None:
    path = write_registry(kb_directory, {'default': 'kb/example-en.yaml'})
    registry = await load_registry(path)
    mapping = json.loads(path.read_text(encoding='utf-8'))
    mapping['evil'] = '../../outside.yaml'
    path.write_text(json.dumps(mapping), encoding='utf-8')

    with pytest.raises(RegistryError, match='traversal'):
        await registry.select('evil')


# === Webhook selection ===


def test_webhook_selects_the_base_by_client_header(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_registry(
        kb_directory,
        {'default': 'kb/example-en.yaml', 'client-ru': 'kb/example-ru.yaml'},
    )
    registry_env(monkeypatch, path)
    fake = FakeModelClient([RU_REPLY])

    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/webhooks/crm/messages',
            headers={'X-Client-Id': 'client-ru'},
            data={'message[add][0][text]': 'Price?'},
        )

    assert response.status_code == 202
    assert response.json() == {'accepted': True}
    prompt = fake.calls[0][0][0]['content']
    assert 'Эфиопия Сидамо' in prompt
    assert '890 RUB' in prompt


# === Request time failures ===


def test_registry_failure_answers_the_envelope(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_registry(kb_directory, {'default': 'kb/example-en.yaml'})
    registry_env(monkeypatch, path)

    with TestClient(create_app(client=FakeModelClient([]))) as client:
        path.write_text('{"default": ', encoding='utf-8')
        response = client.post('/api/suggest', json={'message': 'Hello'})

    assert response.status_code == 500
    assert response.json() == {
        'code': 'registry_error',
        'message': 'the knowledge base registry is invalid',
    }


def test_base_failure_answers_the_envelope(
    kb_directory: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = write_registry(kb_directory, {'default': 'kb/example-en.yaml'})
    registry_env(monkeypatch, path)

    with TestClient(create_app(client=FakeModelClient([]))) as client:
        base = kb_directory / 'kb' / 'example-en.yaml'
        base.write_text('company: Broken\n', encoding='utf-8')
        response = client.post('/api/suggest', json={'message': 'Hello'})

    assert response.status_code == 500
    assert response.json() == {
        'code': 'kb_error',
        'message': 'the knowledge base is invalid',
    }

"""Demo catalogue selection tests."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from reply_assistant.app import create_app
from reply_assistant.registry import RegistryError
from reply_assistant.settings import Settings
from tests.acceptance.fakes import FakeModelClient
from tests.acceptance.test_multi_kb import (
    EN_REPLY,
    RU_REPLY,
    registry_env,
    write_registry,
)
from tests.editor_runtime import run_editor_page
from tests.test_page_language import suggestion

KB = Path(__file__).parents[1] / 'kb'


@pytest.fixture
def demo_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Configure two demo catalogues."""
    bases = tmp_path / 'kb'
    bases.mkdir()
    for name in ('example-en.yaml', 'example-ru.yaml'):
        (bases / name).write_bytes((KB / name).read_bytes())
    registry = write_registry(
        tmp_path,
        {
            'demo-en': 'kb/example-en.yaml',
            'demo-ru': 'kb/example-ru.yaml',
        },
    )
    registry_env(monkeypatch, registry)
    monkeypatch.setenv(
        'REPLY_ASSISTANT_DEMO_CATALOGUES',
        '{"en":"demo-en","ru":"demo-ru"}',
    )
    return registry


@pytest.mark.parametrize(
    ('language', 'reply', 'company'),
    [('ru', RU_REPLY, "Обжарочная 'Зерно'"), ('en', EN_REPLY, 'Clayfield Minerals')],
    ids=['ru', 'en'],
)
def test_language_selects_the_registered_catalogue(
    demo_registry: Path,
    language: str,
    reply: str,
    company: str,
) -> None:
    fake = FakeModelClient([reply])
    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest',
            json={'message': 'Custom question'},
            headers={'X-Catalogue-Language': language},
        )
    assert response.status_code == 200
    base = fake.calls[0][0][0]['content'].split('<knowledge_base>\n')[1]
    data = json.loads(base.split('\n</knowledge_base>')[0])
    assert data['company'] == company
    assert data['language'] == language


@pytest.mark.parametrize('defect', ['missing', 'missing-en', 'wrong-language'])
def test_changed_mapping_refuses_the_wrong_catalogue(
    demo_registry: Path,
    defect: str,
) -> None:
    fake = FakeModelClient([])
    with TestClient(create_app(client=fake)) as client:
        mapping = json.loads(demo_registry.read_text())
        if defect == 'missing':
            del mapping['demo-ru']
        elif defect == 'missing-en':
            del mapping['demo-en']
        else:
            mapping['demo-ru'] = 'kb/example-en.yaml'
        demo_registry.write_text(json.dumps(mapping))
        response = client.post(
            '/api/suggest',
            json={'message': 'Question'},
            headers={'X-Catalogue-Language': 'en' if defect == 'missing-en' else 'ru'},
        )
    assert response.status_code == 503
    assert response.json()['code'] == 'catalogue_unavailable'
    assert fake.calls == []


@pytest.mark.parametrize(
    'headers',
    [
        {'X-Catalogue-Language': 'fr'},
        {'X-Catalogue-Language': 'ru', 'X-Client-Id': 'demo-en'},
    ],
)
def test_invalid_demo_selection_never_calls_the_model(
    demo_registry: Path,
    headers: dict[str, str],
) -> None:
    fake = FakeModelClient([])
    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest', json={'message': 'Question'}, headers=headers
        )
    assert response.status_code == 400
    assert response.json()['code'] == 'invalid_catalogue_selection'
    assert fake.calls == []


def test_legacy_unknown_client_keeps_the_default(demo_registry: Path) -> None:
    fake = FakeModelClient([EN_REPLY])
    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest',
            json={'message': 'Question'},
            headers={'X-Client-Id': 'unknown'},
        )
    assert response.status_code == 200
    assert 'Clayfield Minerals' in fake.calls[0][0][0]['content']


def test_request_language_is_frozen_and_result_language_is_retained() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Original question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
            {'kind': 'wait'},
            {'kind': 'set', 'id': 'customer-input', 'value': 'Next question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
        ],
        responses=[
            {'hang': True, 'body': suggestion('Original English response')},
            {'body': suggestion('Следующий русский ответ')},
        ],
        watch=('reply-language',),
    )
    assert [r['headers']['x-catalogue-language'] for r in result['requests']] == [
        'en',
        'ru',
    ]
    assert result['trace'][3]['watch']['reply-language']['text'] == (
        'Язык ответа: английский'
    )
    assert result['trace'][-1]['watch']['reply-language']['text'] == (
        'Язык ответа: русский'
    )
    assert result['reply'] == 'Следующий русский ответ'


@pytest.mark.parametrize('language', ['en', 'ru'])
def test_stored_language_controls_the_first_request(language: str) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Custom question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
        ],
        responses=[{'body': suggestion('A response')}],
        storage={'interface-language': language},
    )
    assert result['requests'][0]['headers']['x-catalogue-language'] == language
    assert result['requests'][0]['body'] == '{"message":"Custom question"}'


@pytest.mark.parametrize(
    'mapping',
    [
        {'en': 'demo-en'},
        {'en': 'demo-en', 'ru': ' '},
    ],
)
def test_invalid_language_configuration_is_refused(mapping: dict[str, str]) -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(
            provider_api_key='synthetic-key',
            provider_base_url='https://fake.test',
            provider_model='fake',
            kb_registry=Path('registry.json'),
            demo_catalogues=mapping,
        )
    assert caught.value.errors()[0]['type'] == 'invalid_demo_catalogues'


def test_catalogue_language_mismatch_prevents_startup(demo_registry: Path) -> None:
    mapping = json.loads(demo_registry.read_text())
    mapping['demo-ru'] = 'kb/example-en.yaml'
    demo_registry.write_text(json.dumps(mapping))
    with (
        pytest.raises(RegistryError, match='demo catalogue language is invalid'),
        TestClient(create_app(client=FakeModelClient([]))) as client,
    ):
        client.get('/health')


def test_demo_selection_cannot_bypass_the_token(
    demo_registry: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv('REPLY_ASSISTANT_API_TOKEN', 'synthetic-token')
    fake = FakeModelClient([])
    with TestClient(create_app(client=fake)) as client:
        response = client.post(
            '/api/suggest',
            json={'message': 'Question'},
            headers={'X-Catalogue-Language': 'ru'},
        )
    assert response.status_code == 401
    assert fake.calls == []


def test_unavailable_catalogue_message_follows_interface_language() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
        ],
        responses=[{'status': 503, 'body': {'code': 'catalogue_unavailable'}}],
        watch=('assistant-state',),
    )
    assert result['trace'][2]['watch']['assistant-state']['text'] == (
        'The catalogue for this language is not configured.'
    )
    assert result['trace'][-1]['watch']['assistant-state']['text'] == (
        'Каталог для этого языка не настроен.'
    )

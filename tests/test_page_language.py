"""Interface language picker page tests."""

from importlib.resources import files
from typing import Any

import pytest

from tests.editor_runtime import run_editor_page

# === Data ===

WAITING_RU = 'Ждём сообщение от клиента.'
LOADING_RU = 'Ассистент думает…'
NETWORK_RU = 'Ошибка: не удалось связаться \u0441 ассистентом.'
ACCESS_RU = 'Доступ запрещён: проверьте ссылку на демо и API-токен.'
CHECK_PRODUCT_RU = 'Товар существует'
USAGE_INPUT_RU = 'Входные токены'
FALLBACK_NOTICE_RU = 'Использование (Переключение провайдера)'
MANAGER_PLACEHOLDER_RU = 'Напишите ответ клиенту'
CUSTOMER_PLACEHOLDER_RU = 'Новое сообщение от клиента'
EXPAND_TITLE_RU = 'Развернуть редактор ответа'
RECEIVE_RU = 'Принять'
YOU_RU = 'Вы'
CONTACT_RU = 'Анна Петрова'
MATCH_FOUND_RU = 'найдено'
DRAFT = 'Draft line one\nDraft line two'


def page_source() -> str:
    """Read served page source."""
    return (
        files('reply_assistant')
        .joinpath('static', 'index.html')
        .read_text(encoding='utf-8')
    )


def suggestion(reply_text: str) -> dict[str, Any]:
    """Build one scripted suggestion."""
    return {
        'customer_reply': reply_text,
        'upsell_product_id': 'ZEO-200',
        'upsell_hint': 'Scripted manager hint.',
        'kb_match': 'found',
        'checks': {'rejected': [], 'disclaimer_appended': False},
        'usage': {
            'input_tokens': 2,
            'output_tokens': 3,
            'provider': 'fake',
            'attempts': 1,
        },
    }


# === Picker ===


def test_header_declares_a_labelled_picker_with_both_languages() -> None:
    source = page_source()

    assert '<label class="lang-picker" for="language-select">' in source
    assert '<select id="language-select">' in source
    assert '<option value="en">English</option>' in source
    assert '<option value="ru">Русский</option>' in source
    assert '.lang-picker select {\n  min-height: var(--min-touch);' in source


@pytest.mark.parametrize('button', ['toggle-editor', 'focus-editor'])
def test_picker_stays_available_in_every_workspace_mode(button: str) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'click', 'id': button},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
        ],
        responses=[],
        watch=('language-select',),
    )

    switched = result['trace'][1]['watch']['language-select']
    assert switched['hidden'] is False
    assert switched['value'] == 'ru'
    assert result['trace'][1]['documentLang'] == 'ru'


# === Switching ===


def test_switch_rewords_page_copy_and_document_language() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
            {'kind': 'change', 'id': 'language-select', 'value': 'en'},
        ],
        responses=[],
        watch=(
            'language-select',
            'chat-input',
            'customer-input',
            'toggle-editor',
            'add-customer',
            'assistant-state',
        ),
    )

    russian = result['trace'][0]['watch']
    assert result['trace'][0]['documentLang'] == 'ru'
    assert russian['language-select']['value'] == 'ru'
    assert russian['chat-input']['attributes']['placeholder'] == (
        MANAGER_PLACEHOLDER_RU
    )
    assert russian['customer-input']['attributes']['placeholder'] == (
        CUSTOMER_PLACEHOLDER_RU
    )
    assert russian['toggle-editor']['attributes']['title'] == EXPAND_TITLE_RU
    assert russian['add-customer']['text'] == RECEIVE_RU
    assert russian['assistant-state']['text'] == WAITING_RU
    english = result['trace'][1]['watch']
    assert result['trace'][1]['documentLang'] == 'en'
    assert english['assistant-state']['text'] == 'Waiting for a customer message.'
    assert english['chat-input']['attributes']['placeholder'] == (
        'Write a reply to the customer'
    )
    assert result['requests'] == []


def test_switch_rewords_authors_of_future_messages() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
            {'kind': 'set', 'id': 'chat-input', 'value': 'Ready to ship.'},
            {'kind': 'key', 'id': 'chat-input', 'key': 'Enter', 'ctrl': True},
            {'kind': 'set', 'id': 'customer-input', 'value': 'Second question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
        ],
        responses=[{'body': suggestion('Fine.')}],
    )

    assert [message['author'] for message in result['messages'][2:]] == [
        YOU_RU,
        CONTACT_RU,
    ]


# === State ===


def test_switch_during_a_pending_request_rewords_loading_and_settles_once() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
            {'kind': 'wait'},
        ],
        responses=[{'hang': True, 'body': suggestion('Held reply.')}],
        watch=('assistant-state', 'add-customer'),
    )

    switched = result['trace'][2]['watch']
    assert switched['assistant-state']['text'] == LOADING_RU
    assert switched['assistant-state']['className'] == 'loading'
    assert switched['add-customer']['disabled'] is True
    assert len(result['requests']) == 1
    assert result['reply'] == 'Held reply.'
    assert result['trace'][3]['watch']['add-customer']['disabled'] is False
    assert result['usage'][0]['label'] == USAGE_INPUT_RU


@pytest.mark.parametrize(
    ('response', 'english', 'russian'),
    [
        (
            {'error': 'network down'},
            'Error: could not reach the assistant.',
            NETWORK_RU,
        ),
        (
            {'status': 401},
            'Access denied: check the demo link and the API token.',
            ACCESS_RU,
        ),
    ],
    ids=['network', 'access'],
)
def test_switch_rewords_error_states(
    response: dict[str, Any], english: str, russian: str
) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
        ],
        responses=[response],
        watch=('assistant-state',),
    )

    assert result['trace'][2]['watch']['assistant-state']['text'] == english
    failed = result['trace'][3]['watch']['assistant-state']
    assert failed['text'] == russian
    assert failed['className'] == 'error'


def test_switch_rewords_checks_usage_and_the_fallback_notice() -> None:
    first = suggestion('First draft.')
    first['usage']['fallbacks'] = [{'primary': 'primary', 'secondary': 'secondary'}]
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'First'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
        ],
        responses=[{'body': first}],
        watch=('usage-summary', 'usage-details', 'kb-match'),
    )

    assert (
        result['trace'][2]['watch']['usage-summary']['text']
        == 'Usage (Provider fallback)'
    )
    switched = result['trace'][3]['watch']
    assert switched['usage-summary']['text'] == FALLBACK_NOTICE_RU
    assert 'open' in switched['usage-details']['attributes']
    assert switched['kb-match']['text'] == MATCH_FOUND_RU
    assert CHECK_PRODUCT_RU in [row['name'] for row in result['checks']]
    assert USAGE_INPUT_RU in [row['label'] for row in result['usage']]
    assert result['reply'] == 'First draft.'
    assert result['hint'] == 'ZEO-200 Scripted manager hint.'


def test_switch_preserves_inputs_mode_selection_and_transcript() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'set', 'id': 'customer-input', 'value': 'Unsent question'},
            {'kind': 'set', 'id': 'chat-input', 'value': DRAFT},
            {'kind': 'select', 'id': 'chat-input', 'start': 5, 'end': 9},
            {'kind': 'scroll', 'id': 'chat-input', 'top': 42},
            {'kind': 'click', 'id': 'toggle-editor'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
        ],
        responses=[{'body': suggestion('Kept draft reply.')}],
        watch=(
            'customer-input',
            'chat-input',
            'workspace',
            'toggle-editor',
            'usage-details',
            'assistant-result',
        ),
    )

    switched = result['trace'][-1]['watch']
    assert switched['customer-input']['value'] == 'Unsent question'
    assert switched['chat-input']['value'] == DRAFT
    assert switched['chat-input']['selectionStart'] == 5
    assert switched['chat-input']['selectionEnd'] == 9
    assert switched['chat-input']['scrollTop'] == 42
    assert switched['workspace']['className'] == 'workspace editor-expanded'
    assert switched['toggle-editor']['attributes']['aria-expanded'] == 'true'
    assert switched['assistant-result']['hidden'] is False
    assert 'open' in switched['usage-details']['attributes']
    assert result['reply'] == 'Kept draft reply.'
    assert [message['author'] for message in result['messages']] == [
        'Anna Petrova',
        'You',
        'Anna Petrova',
    ]
    assert [message['text'] for message in result['messages']] == [
        'Hello! Do you have the zeolite powder in stock?',
        'Hello! Yes, it is in the warehouse and ready to ship.',
        'Question',
    ]


# === Persistence ===


@pytest.mark.parametrize(
    ('stored', 'document_language', 'expected'),
    [
        ({'interface-language': 'ru'}, 'en', 'ru'),
        ({'interface-language': 'de'}, 'en', 'en'),
        ({'interface-language': 'fr'}, 'ru', 'ru'),
        ({'interface-language': ''}, 'ru', 'ru'),
    ],
    ids=['applied', 'invalid_falls_back', 'invalid_keeps_base', 'empty_keeps_base'],
)
def test_stored_preference_is_validated_before_it_is_applied(
    stored: dict[str, str], document_language: str, expected: str
) -> None:
    result = run_editor_page(
        steps=[{'kind': 'wait'}],
        responses=[],
        language=document_language,
        storage=stored,
        watch=('language-select', 'assistant-state'),
    )

    opening = result['trace'][0]['watch']
    assert result['documentLang'] == expected
    assert opening['language-select']['value'] == expected
    assert opening['assistant-state']['text'] == (
        WAITING_RU if expected == 'ru' else 'Waiting for a customer message.'
    )


def test_only_the_language_choice_is_persisted() -> None:
    untouched = run_editor_page(
        steps=[],
        responses=[],
        storage={'interface-language': 'ru'},
    )
    switched = run_editor_page(
        steps=[
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
            {'kind': 'change', 'id': 'language-select', 'value': 'en'},
        ],
        responses=[],
    )

    assert untouched['storage'] == []
    assert switched['storage'] == [
        ['interface-language', 'ru'],
        ['interface-language', 'en'],
    ]


def test_blocked_storage_does_not_block_editing_or_receiving() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'set', 'id': 'chat-input', 'value': 'Still editable.'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
        ],
        responses=[{'body': suggestion('Fine.')}],
        storage_blocked=True,
        watch=('chat-input', 'language-select'),
    )

    assert len(result['requests']) == 1
    assert result['reply'] == 'Fine.'
    final = result['trace'][-1]['watch']
    assert final['chat-input']['value'] == 'Still editable.'
    assert final['language-select']['value'] == 'ru'
    assert result['documentLang'] == 'ru'
    assert result['storage'] == []

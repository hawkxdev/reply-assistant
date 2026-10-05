"""Editor workspace page tests."""

import json
from importlib.resources import files
from typing import Any

import pytest

from tests.editor_runtime import run_editor_page

# === Data ===

MULTILINE_REPLY = (
    'Dear customer, the powder is in stock.\n'
    '\n'
    'It ships from the warehouse on the next business day.\n'
    'A 200 gram jar lasts one full course.\n'
    'The courier delivers within two working days.\n'
    'You can reply here with any further question.\n'
    'Thank you for your interest in our shop.\n'
)
CHECKS_NOTE_EN = 'Checks show configured validation, not proof of factual accuracy.'
CHECKS_NOTE_RU = (
    'Проверки показывают настроенную валидацию, '
    'но не доказательство фактической точности.'
)
NETWORK_ERROR_RU = 'Ошибка: не удалось связаться \u0441 ассистентом.'
DRAFT = 'Draft line one\nDraft line two'
CLAMPED_DRAFT = '\n'.join(
    f'Draft line {index} for editing position' for index in range(17)
)
LONG_INSERTION = (
    'Dear customer, this is the first paragraph.\n\n'
    + 'A detailed draft with product information. ' * 70
    + '\n\nThis product is a food supplement and is not a medicine.'
)


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
        'upsell_product_id': None,
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


# === Editor ===


def test_insert_grows_the_editor_to_show_the_first_paragraph() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Any question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'click', 'id': 'insert-reply'},
        ],
        responses=[{'body': suggestion(MULTILINE_REPLY)}],
        watch=('chat-input',),
    )

    editor = result['trace'][-1]['watch']['chat-input']
    assert editor['value'] == MULTILINE_REPLY
    assert int(editor['attributes']['rows']) >= 5
    assert editor['scrollTop'] == 0


def test_ctrl_enter_adds_the_manager_reply_and_clears_the_editor() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': 'Ready to ship today.'},
            {'kind': 'key', 'id': 'chat-input', 'key': 'Enter', 'ctrl': True},
        ],
        responses=[],
        watch=('chat-input',),
    )

    assert result['requests'] == []
    assert result['trace'][-1]['defaultPrevented'] is True
    editor = result['trace'][-1]['watch']['chat-input']
    assert editor['value'] == ''
    assert editor['attributes']['rows'] == '3'
    added = [
        message
        for message in result['messages']
        if 'outgoing' in message['className']
        and message['text'] == 'Ready to ship today.'
    ]
    assert [message['author'] for message in added] == ['You']


def test_plain_and_shift_enter_keep_inserting_new_lines() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': 'First line'},
            {'kind': 'key', 'id': 'chat-input', 'key': 'Enter'},
            {'kind': 'key', 'id': 'chat-input', 'key': 'Enter', 'shift': True},
        ],
        responses=[],
        watch=('chat-input',),
    )

    blocked = [entry['defaultPrevented'] for entry in result['trace'][-2:]]
    assert blocked == [False, False]
    assert result['requests'] == []
    assert len(result['messages']) == 2


def test_expand_hides_the_customer_form_and_keeps_its_value() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Unsent question'},
            {'kind': 'set', 'id': 'chat-input', 'value': 'Draft stays.'},
            {'kind': 'click', 'id': 'toggle-editor'},
            {'kind': 'click', 'id': 'toggle-editor'},
        ],
        responses=[],
        watch=(
            'customer-writer',
            'customer-input',
            'chat-input',
            'workspace',
            'toggle-editor',
        ),
    )

    during = result['trace'][2]['watch']
    assert during['customer-writer']['hidden'] is True
    assert during['customer-input']['value'] == 'Unsent question'
    assert 'editor-expanded' in during['workspace']['className']
    assert during['toggle-editor']['text'] == 'Collapse'
    assert during['toggle-editor']['attributes']['aria-expanded'] == 'true'
    restored = result['trace'][3]['watch']
    assert restored['customer-writer']['hidden'] is False
    assert restored['customer-input']['value'] == 'Unsent question'
    assert restored['chat-input']['value'] == 'Draft stays.'
    assert restored['workspace']['className'] == 'workspace'
    assert restored['toggle-editor']['attributes']['aria-expanded'] == 'false'


def test_focus_mode_and_escape_keep_the_draft_and_selection() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': DRAFT},
            {'kind': 'select', 'id': 'chat-input', 'start': 5, 'end': 9},
            {'kind': 'scroll', 'id': 'chat-input', 'top': 37},
            {'kind': 'click', 'id': 'focus-editor'},
            {'kind': 'key', 'id': 'chat-input', 'key': 'Escape'},
        ],
        responses=[],
        watch=(
            'chat-input',
            'workspace',
            'deal',
            'assistant',
            'customer-writer',
            'focus-editor',
        ),
    )

    focused = result['trace'][3]['watch']
    assert 'editor-focus' in focused['workspace']['className']
    assert focused['deal']['hidden'] is True
    assert focused['assistant']['hidden'] is False
    assert focused['customer-writer']['hidden'] is True
    assert focused['focus-editor']['text'] == 'Exit focus'
    assert focused['focus-editor']['attributes']['aria-pressed'] == 'true'
    back = result['trace'][4]['watch']
    assert back['workspace']['className'] == 'workspace'
    assert back['deal']['hidden'] is False
    assert back['customer-writer']['hidden'] is False
    assert back['chat-input']['value'] == DRAFT
    assert back['chat-input']['selectionStart'] == 5
    assert back['chat-input']['selectionEnd'] == 9
    assert back['chat-input']['scrollTop'] == 37
    assert back['focus-editor']['attributes']['aria-pressed'] == 'false'


# === Loading ===


def test_loading_blocks_a_duplicate_receive_and_keeps_the_next_question() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'First question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'set', 'id': 'customer-input', 'value': 'Second question'},
            {'kind': 'wait'},
        ],
        responses=[{'hang': True, 'body': suggestion('Held reply.')}],
        watch=('add-customer', 'customer-input'),
    )

    assert result['trace'][1]['watch']['add-customer']['disabled'] is True
    assert result['trace'][2]['refused'] is True
    assert result['trace'][2]['watch']['add-customer']['disabled'] is True
    settled = result['trace'][4]['watch']
    assert settled['add-customer']['disabled'] is False
    assert settled['customer-input']['value'] == 'Second question'
    assert len(result['requests']) == 1
    assert result['reply'] == 'Held reply.'


@pytest.mark.parametrize(
    ('language', 'error'),
    [('en', 'Error: could not reach the assistant.'), ('ru', NETWORK_ERROR_RU)],
    ids=['en', 'ru'],
)
def test_network_error_recovers_the_receive_control(language: str, error: str) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
        ],
        responses=[{'error': 'network down'}],
        language=language,
        watch=('add-customer',),
    )

    assert result['trace'][1]['watch']['add-customer']['disabled'] is True
    assert result['state'] == error
    assert result['trace'][2]['watch']['add-customer']['disabled'] is False


# === Customer input ===


def test_customer_paste_stays_multiline_and_grows_within_its_cap() -> None:
    pasted = 'ab\n' * 666 + 'cd'
    assert len(pasted) == 2000
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': pasted},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
        ],
        responses=[{'body': suggestion('Fine.')}],
        watch=('customer-input',),
    )

    assert result['trace'][0]['watch']['customer-input']['attributes']['rows'] == '4'
    assert len(result['requests']) == 1
    assert json.loads(result['requests'][0]['body']) == {'message': pasted}
    incoming = [
        message
        for message in result['messages']
        if 'incoming' in message['className'] and message['text'] == pasted
    ]
    assert [message['author'] for message in incoming] == ['Anna Petrova']


# === Page contract ===


def test_page_declares_the_editor_contract_ids_and_limits() -> None:
    source = page_source()

    assert '<textarea id="customer-input" maxlength="2000"' in source
    for part in ('toggle-editor', 'focus-editor', 'customer-writer', 'workspace'):
        assert f'id="{part}"' in source


def test_page_styles_responsive_modes_and_accessible_controls() -> None:
    source = page_source()

    for needle in (
        '@media',
        'grid-template-areas',
        'editor-focus',
        'editor-expanded',
        'field-sizing: content',
        ':focus-visible',
        '--min-touch: 44px',
        'var(--min-touch)',
        'data-i18n-title',
        'overflow-wrap: anywhere',
    ):
        assert needle in source


@pytest.mark.parametrize(
    ('english', 'russian'),
    [
        ("managerButton: 'Add to demo'", "managerButton: 'Добавить в демо'"),
        ("expand: 'Expand'", "expand: 'Развернуть'"),
        ("collapse: 'Collapse'", "collapse: 'Свернуть'"),
        ("focusOn: 'Focus'", "focusOn: 'Фокус'"),
        ("focusOff: 'Exit focus'", "focusOff: 'Выйти из фокуса'"),
        (f'checksNote: {CHECKS_NOTE_EN!r}', f'checksNote: {CHECKS_NOTE_RU!r}'),
    ],
    ids=['add', 'expand', 'collapse', 'focus', 'unfocus', 'checks_note'],
)
def test_new_editor_copy_exists_in_both_languages(english: str, russian: str) -> None:
    source = page_source()

    assert english in source
    assert russian in source


# === Native browser regressions ===


@pytest.mark.parametrize('button', ['toggle-editor', 'focus-editor'])
def test_escape_exits_after_keyboard_button_activation(button: str) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'key', 'id': button, 'key': 'Enter'},
            {'kind': 'key', 'id': 'active', 'key': 'Escape'},
        ],
        responses=[],
        watch=('workspace',),
    )

    assert result['trace'][-1]['watch']['workspace']['className'] == 'workspace'


def test_insertion_resets_the_native_caret_and_focus_scroll() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'Question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'click', 'id': 'insert-reply'},
            {'kind': 'wait'},
        ],
        responses=[{'body': suggestion(LONG_INSERTION)}],
        watch=('chat-input',),
        geometry={'normal': 250, 'expanded': 334, 'focused': 358, 'scrollHeight': 645},
    )

    editor = result['trace'][-1]['watch']['chat-input']
    assert editor['selectionStart'] == 0
    assert editor['selectionEnd'] == 0
    assert editor['scrollTop'] == 0


@pytest.mark.parametrize('button', ['toggle-editor', 'focus-editor'])
def test_mode_round_trip_restores_a_clamped_scroll_anchor(button: str) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': CLAMPED_DRAFT},
            {'kind': 'select', 'id': 'chat-input', 'start': 5, 'end': 9},
            {'kind': 'scroll', 'id': 'chat-input', 'top': 110},
            {'kind': 'wait'},
            {'kind': 'click', 'id': button},
            {'kind': 'wait'},
            {'kind': 'key', 'id': 'chat-input', 'key': 'Escape'},
            {'kind': 'wait'},
        ],
        responses=[],
        watch=('chat-input',),
        geometry={'normal': 250, 'expanded': 334, 'focused': 358, 'scrollHeight': 361},
    )

    editor = result['trace'][-1]['watch']['chat-input']
    assert editor['value'] == CLAMPED_DRAFT
    assert editor['selectionStart'] == 5
    assert editor['selectionEnd'] == 9
    assert editor['scrollTop'] == 110


def test_focus_mode_reveals_the_relocated_editor() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': CLAMPED_DRAFT},
            {'kind': 'click', 'id': 'focus-editor'},
        ],
        responses=[],
        watch=('chat-input',),
        geometry={
            'normal': 250,
            'expanded': 334,
            'focused': 358,
            'scrollHeight': 361,
            'relocate': True,
        },
    )

    assert result['trace'][-1]['watch']['chat-input']['inViewport'] is True


def test_resize_round_trip_restores_a_clamped_scroll_anchor() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': CLAMPED_DRAFT},
            {'kind': 'scroll', 'id': 'chat-input', 'top': 110},
            {'kind': 'wait'},
            {'kind': 'resize', 'geometry': {'normal': 400}},
            {'kind': 'resize', 'geometry': {'normal': 250}},
        ],
        responses=[],
        watch=('chat-input',),
        geometry={'normal': 250, 'expanded': 334, 'focused': 358, 'scrollHeight': 361},
    )

    assert result['trace'][-1]['watch']['chat-input']['scrollTop'] == 110


def test_user_scroll_in_expanded_mode_replaces_the_saved_anchor() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': CLAMPED_DRAFT},
            {'kind': 'scroll', 'id': 'chat-input', 'top': 110},
            {'kind': 'wait'},
            {'kind': 'click', 'id': 'toggle-editor'},
            {'kind': 'wait'},
            {'kind': 'scroll', 'id': 'chat-input', 'top': 10},
            {'kind': 'wait'},
            {'kind': 'scroll', 'id': 'chat-input', 'top': 27},
            {'kind': 'wait'},
            {'kind': 'key', 'id': 'chat-input', 'key': 'Escape'},
            {'kind': 'wait'},
        ],
        responses=[],
        watch=('chat-input',),
        geometry={'normal': 250, 'expanded': 334, 'focused': 358, 'scrollHeight': 361},
    )

    assert result['trace'][-1]['watch']['chat-input']['scrollTop'] == 27


@pytest.mark.parametrize(
    ('language', 'notice', 'plain'),
    [
        ('en', 'Usage (Provider fallback)', 'Usage'),
        ('ru', 'Использование (Переключение провайдера)', 'Использование'),
    ],
    ids=['en', 'ru'],
)
def test_fallback_notice_survives_details_and_clears_on_next_answer(
    language: str,
    notice: str,
    plain: str,
) -> None:
    first = suggestion('First draft.')
    first['usage']['fallbacks'] = [{'primary': 'primary', 'secondary': 'secondary'}]
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'First'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'set', 'id': 'customer-input', 'value': 'Second'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
        ],
        responses=[{'body': first}, {'body': suggestion('Second draft.')}],
        language=language,
        watch=('usage-summary',),
    )

    assert result['trace'][2]['watch']['usage-summary']['text'] == notice
    assert result['trace'][-1]['watch']['usage-summary']['text'] == plain

"""Example question interaction tests."""

import pytest

from tests.editor_runtime import run_editor_page
from tests.test_page_language import suggestion


@pytest.mark.parametrize(
    ('language', 'button', 'question'),
    [
        ('ru', 'question-selection', 'Помогите подобрать товар под мой запрос.'),
        ('ru', 'question-upsell', 'Что ещё стоит добавить к заказу?'),
        ('ru', 'question-unknown', 'Вы предлагаете ремонт бытовой техники?'),
        ('en', 'question-selection', 'Could you help me choose a suitable product?'),
        ('en', 'question-upsell', 'What else would go well with my order?'),
        ('en', 'question-unknown', 'Do you offer home appliance repairs?'),
    ],
)
def test_example_fills_only_the_question(
    language: str,
    button: str,
    question: str,
) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'chat-input', 'value': 'My working draft'},
            {'kind': 'click', 'id': 'toggle-editor'},
            {'kind': 'click', 'id': button},
        ],
        responses=[],
        language=language,
        watch=('customer-input', 'chat-input', 'toggle-editor', 'assistant-result'),
    )

    final = result['trace'][-1]['watch']
    assert final['customer-input']['value'] == question
    assert final['chat-input']['value'] == 'My working draft'
    assert final['toggle-editor']['attributes']['aria-expanded'] == 'false'
    assert result['requests'] == []
    assert result['reply'] == ''
    assert result['activeElement'] == 'customer-input'


def test_selected_example_submits_the_edited_question() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'click', 'id': 'question-selection'},
            {'kind': 'set', 'id': 'customer-input', 'value': 'My specific question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
        ],
        responses=[{'body': suggestion('A unique model response')}],
        watch=('ready-status',),
    )

    assert [request['body'] for request in result['requests']] == [
        '{"message":"My specific question"}',
    ]
    assert result['reply'] == 'A unique model response'
    assert result['trace'][-1]['watch']['ready-status']['hidden'] is False


def test_examples_preserve_a_visible_model_result() -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'set', 'id': 'customer-input', 'value': 'A custom question'},
            {'kind': 'click', 'id': 'add-customer'},
            {'kind': 'wait'},
            {'kind': 'click', 'id': 'question-upsell'},
        ],
        responses=[{'body': suggestion('Preserved model reply')}],
        watch=('assistant-result',),
    )

    assert len(result['requests']) == 1
    assert result['reply'] == 'Preserved model reply'
    assert result['trace'][-1]['watch']['assistant-result']['hidden'] is False


def test_initial_workspace_has_no_generated_reply() -> None:
    result = run_editor_page(
        steps=[{'kind': 'wait'}],
        responses=[],
        watch=('assistant-result', 'ready-status'),
    )

    assert result['requests'] == []
    assert result['messages'] == []
    assert result['reply'] == ''
    assert result['trace'][0]['watch']['assistant-result']['hidden'] is True
    assert result['trace'][0]['watch']['ready-status']['hidden'] is True


@pytest.mark.parametrize(
    ('target', 'english', 'russian'),
    [
        ('examples', 'Example questions', 'Примеры вопросов'),
        ('deal', 'Customer details', '\u041e клиенте'),
    ],
)
def test_landmark_names_follow_interface_language(
    target: str,
    english: str,
    russian: str,
) -> None:
    result = run_editor_page(
        steps=[
            {'kind': 'wait'},
            {'kind': 'change', 'id': 'language-select', 'value': 'ru'},
            {'kind': 'change', 'id': 'language-select', 'value': 'en'},
        ],
        responses=[],
        watch=(target,),
    )

    assert [step['watch'][target]['accessibleName'] for step in result['trace']] == [
        english,
        russian,
        english,
    ]

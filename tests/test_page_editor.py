"""Exercise draft editor behavior."""

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.page_runtime import RUNTIME

# === Runtime ===

PREPARE = """
for (const element of elements.values()) {
  element.style = {};
  element.scrollHeight = 180;
  element.scrollTop = 0;
  element.selectionStart = 0;
  element.selectionEnd = 0;
  element.setSelectionRange = function(start, end) {
    this.selectionStart = start;
    this.selectionEnd = end;
  };
}
"""


def observe_editor(actions: str) -> dict[str, Any]:
    """Execute actual editor events."""
    node = shutil.which('node')
    if node is None:
        raise RuntimeError('Node.js is required for editor tests')
    html = (
        Path(__file__).parents[1] / 'src/reply_assistant/static/index.html'
    ).read_text(encoding='utf-8')
    runtime = RUNTIME.replace(
        'vm.runInContext(input.script, context, {timeout: 1000});',
        PREPARE
        + 'vm.runInContext(input.script, context, {timeout: 1000});'
        + 'vm.runInContext(input.actions, context, {timeout: 1000});',
    ).replace(
        '    requests, logs, storage, cookies,',
        '    requests, logs, storage, cookies, editor: context.editorObservation,',
    )
    payload: dict[str, Any] = {
        'html': html,
        'script': '\n'.join(
            re.findall(r'<script\b[^>]*>(.*?)</script>', html, re.DOTALL)
        ),
        'actions': actions,
        'suffix': '',
        'language': 'en',
        'expected_token': None,
        'messages': [],
        'failure_message': None,
    }
    completed = subprocess.run(  # noqa: S603
        [node, '-e', runtime],
        input=json.dumps(payload),
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    observed: dict[str, Any] = json.loads(completed.stdout)
    editor_result: dict[str, Any] = observed['editor']
    return editor_result


# === Editing ===


def test_pending_request_keeps_the_next_question_unsubmitted() -> None:
    result = observe_editor("""
customerInput.value = 'First question';
receiveCustomerMessage();
customerInput.value = 'Second question';
receiveCustomerMessage();
globalThis.editorObservation = {count: messages.children.length,
  next: customerInput.value};
""")

    assert result == {'count': 3, 'next': 'Second question'}


def test_enter_keeps_the_draft_for_multiline_editing() -> None:
    result = observe_editor("""
chatInput.value = 'A draft with another paragraph to write.';
let prevented = false;
chatInput.listeners.keydown({key: 'Enter', shiftKey: false,
  ctrlKey: false, metaKey: false, preventDefault: () => { prevented = true; }});
globalThis.editorObservation = {prevented, value: chatInput.value,
  count: messages.children.length};
""")

    assert result == {
        'prevented': False,
        'value': 'A draft with another paragraph to write.',
        'count': 2,
    }


@pytest.mark.parametrize('modifier', ['ctrlKey', 'metaKey'])
def test_modified_enter_adds_the_reply(modifier: str) -> None:
    result = observe_editor(
        """
chatInput.value = 'Reviewed reply.';
let prevented = false;
chatInput.listeners.keydown({key: 'Enter', shiftKey: false,
  """
        + modifier
        + """: true, preventDefault: () => { prevented = true; }});
globalThis.editorObservation = {prevented, value: chatInput.value,
  count: messages.children.length};
"""
    )

    assert result == {'prevented': True, 'value': '', 'count': 3}


def test_input_grows_the_editor_for_a_long_draft() -> None:
    result = observe_editor("""
chatInput.value = 'A long reply.';
chatInput.listeners.input?.({target: chatInput});
globalThis.editorObservation = {height: chatInput.style.height ?? null};
""")

    assert result == {'height': '180px'}


def test_expanding_and_collapsing_preserves_the_edit_selection() -> None:
    result = observe_editor("""
chatInput.value = 'A draft with a selected word.';
chatInput.setSelectionRange(15, 23);
const button = document.getElementById('expand-editor');
button?.listeners.click({target: button});
const wasExpanded = button?.getAttribute('aria-expanded');
const fieldExpanded = document.getElementById('editor')?.getAttribute('data-expanded');
button?.listeners.click({target: button});
globalThis.editorObservation = {expanded: wasExpanded ?? null,
  fieldExpanded: fieldExpanded ?? null,
  collapsed: button?.getAttribute('aria-expanded') ?? null,
  value: chatInput.value, start: chatInput.selectionStart, end: chatInput.selectionEnd};
""")

    assert result == {
        'expanded': 'true',
        'fieldExpanded': 'true',
        'collapsed': 'false',
        'value': 'A draft with a selected word.',
        'start': 15,
        'end': 23,
    }


def test_focus_mode_restores_the_conversation_and_draft() -> None:
    result = observe_editor("""
chatInput.value = 'Keep this unfinished answer.';
chatInput.setSelectionRange(5, 5);
const button = document.getElementById('focus-editor');
button?.listeners.click({target: button});
const wasFocused = document.getElementById('messages').hidden;
button?.listeners.click({target: button});
globalThis.editorObservation = {focused: wasFocused,
  restored: !document.getElementById('messages').hidden,
  value: chatInput.value, start: chatInput.selectionStart};
""")

    assert result == {
        'focused': True,
        'restored': True,
        'value': 'Keep this unfinished answer.',
        'start': 5,
    }


def test_inserting_a_reply_starts_at_the_first_paragraph() -> None:
    result = observe_editor(r"""
lastReply = 'First paragraph.\n\nLast paragraph.';
chatInput.scrollTop = 400;
chatInput.setSelectionRange(8, 12);
document.getElementById('insert-reply').listeners.click({});
globalThis.editorObservation = {value: chatInput.value, scroll: chatInput.scrollTop,
  start: chatInput.selectionStart, end: chatInput.selectionEnd};
""")

    assert result == {
        'value': 'First paragraph.\n\nLast paragraph.',
        'scroll': 0,
        'start': 0,
        'end': 0,
    }

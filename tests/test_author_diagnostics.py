"""Verify private diagnostic projection."""

from scripts.author_diagnostics import summarize


def test_summary_retains_finish_before_vendor_summary_without_text() -> None:
    data = {
        'messages': [
            {'info': {'id': 'first', 'role': 'user'}, 'parts': []},
            {
                'info': {'role': 'assistant', 'parentID': 'first', 'finish': 'length'},
                'parts': [
                    {'type': 'reasoning', 'text': 'PRIVATE'},
                    {
                        'type': 'tool',
                        'state': {'status': 'completed', 'output': 'SECRET'},
                    },
                ],
            },
            {'info': {'id': 'summary', 'role': 'user'}, 'parts': []},
            {
                'info': {'role': 'assistant', 'parentID': 'summary', 'finish': 'stop'},
                'parts': [{'type': 'text', 'text': 'PRIVATE'}],
            },
        ],
    }

    assert summarize(data) == {
        'capture': 'observed',
        'work_finish': 'length',
        'last_finish': 'stop',
        'assistant_messages': 2,
        'completed_tools': 1,
        'failed_tools': 0,
        'pending_tools': 0,
    }


def test_unknown_provider_fields_do_not_escape_projection() -> None:
    data = {
        'messages': [
            {'info': {'id': 'first', 'role': 'user'}},
            {
                'info': {'role': 'assistant', 'parentID': 'first', 'finish': 'SECRET'},
                'parts': [{'type': 'tool', 'state': {'status': 'SECRET'}}],
            },
        ]
    }

    result = summarize(data)

    assert result['work_finish'] == 'unknown'
    assert result['last_finish'] == 'unknown'
    assert 'SECRET' not in str(result)


def test_missing_messages_are_not_reported_as_zero_activity() -> None:
    assert summarize({}) == {'capture': 'unavailable'}
